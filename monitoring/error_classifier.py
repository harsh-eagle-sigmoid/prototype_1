
import re
import psycopg2
from typing import Dict, Optional
from loguru import logger
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv(dotenv_path="/home/lenovo/Desktop/New_tech_demo/.env")

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
DB_NAME     = os.getenv("DB_NAME", "unilever_poc")
DB_USER     = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")

# ── Keyword rules per category ────────────────────────────────────────────
RULES = {
    "SQL_GENERATION": [
        r"syntax error",
        r"invalid sql",
        r"could not parse",
        r"failed to generate",
        r"empty sql",
        r"no sql returned",
        r"unexpected token",
    ],
    "CONTEXT_RETRIEVAL": [
        r"relation .* does not exist",
        r"column .* does not exist",
        r"table .* not found",
        r"schema .* does not exist",
        r"unknown column",
        r"no such table",
    ],
    "DATA_ERROR": [
        r"no rows returned",
        r"empty result",
        r"0 rows",
        r"no data",
        r"null value",
        r"out of range",
        r"invalid input syntax for type",
    ],
    "INTEGRATION": [
        r"connection refused",
        r"timeout",
        r"connection error",
        r"http error",
        r"service unavailable",
        r"could not connect",
        r"max retries",
    ],
    "AGENT_LOGIC": [
        r"incorrect logic",
        r"wrong aggregation",
        r"missing filter",
        r"wrong table",
        r"incorrect join",
    ],
}

# ── Severity rules ────────────────────────────────────────────────────────
SEVERITY_MAP = {
    "SQL_GENERATION":    "high",
    "CONTEXT_RETRIEVAL": "high",
    "DATA_ERROR":        "medium",
    "INTEGRATION":       "critical",
    "AGENT_LOGIC":       "medium",
}


class ErrorClassifier:
    """Rule-based error classification."""

    def classify(self, error_message: str, query_id: Optional[str] = None,
                 evaluation_id: Optional[int] = None) -> Dict:
       
        if not error_message:
            return self._build_result(query_id, evaluation_id, "UNKNOWN", "low", error_message)

        msg_lower = error_message.lower()

        # Match against rules — first match wins
        for category, patterns in RULES.items():
            for pattern in patterns:
                if re.search(pattern, msg_lower):
                    severity = SEVERITY_MAP.get(category, "medium")
                    result   = self._build_result(query_id, evaluation_id, category, severity, error_message)
                    self._store(result)
                    return result

        # No rule matched → default to AGENT_LOGIC
        result = self._build_result(query_id, evaluation_id, "AGENT_LOGIC", "low", error_message)
        self._store(result)
        return result

    # ── Helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _build_result(query_id, evaluation_id, category, severity, error_message) -> Dict:
        suggestions = {
            "SQL_GENERATION":    "Check few-shot examples, add more schema context to prompt",
            "CONTEXT_RETRIEVAL": "Verify schema_info refresh — table/column may have changed",
            "DATA_ERROR":        "Query is valid but data missing — check filters / date range",
            "INTEGRATION":       "Check DB connection / agent HTTP server is running",
            "AGENT_LOGIC":       "Review prompt and few-shot examples for this query pattern",
            "UNKNOWN":           "Manual review needed",
        }
        return {
            "query_id":       query_id,
            "evaluation_id":  evaluation_id,
            "error_category": category,
            "severity":       severity,
            "error_message":  error_message,
            "suggested_fix":  suggestions.get(category, "Manual review"),
            "created_at":     datetime.now().isoformat()
        }

    def _store(self, result: Dict):
        """Store classified error in monitoring.errors."""
        try:
            conn = psycopg2.connect(
                host=DB_HOST, port=DB_PORT, database=DB_NAME,
                user=DB_USER, password=DB_PASSWORD
            )
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO monitoring.errors
                    (query_id, evaluation_id, error_category, error_message,
                     severity, suggested_fix, first_seen, last_seen)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                result["query_id"],
                result["evaluation_id"],
                result["error_category"],
                result["error_message"],
                result["severity"],
                result["suggested_fix"],
                datetime.now(),
                datetime.now()
            ))
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Error storing classification: {e}")
