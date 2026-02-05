
import json
import requests as http
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
import uuid
from datetime import datetime
import decimal
from fastapi import FastAPI, HTTPException, Query, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

from config.settings import settings
from auth.azure_auth import get_current_user, require_auth, AuthUser
from alerts.alert_service import alert_service, AlertType

# ── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Unilever Procurement GPT — API Gateway",
    version="2.0",
    description="Unified gateway with AUTOMATED drift, error, and evaluation pipeline"
)

# ── CORS middleware ──────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Agent base URLs (independent services) ──────────────────────────────────
AGENT_URLS = {
    "spend":  "http://localhost:8001",
    "demand": "http://localhost:8002",
}


# ── Global caches (lazy loaded) ─────────────────────────────────────────────
_drift_detector = None
_error_classifier = None
_ground_truth_cache = None
db_pool = None

@app.on_event("startup")
def startup_event():
    global db_pool
    try:
        db_pool = pool.SimpleConnectionPool(
            1, 20,
            host=settings.DB_HOST, port=settings.DB_PORT,
            database=settings.DB_NAME,
            user=settings.DB_USER, password=settings.DB_PASSWORD
        )
        logger.info("DB Connection Pool initialized")
    except Exception as e:
        logger.error(f"Failed to create DB pool: {e}")

@app.on_event("shutdown")
def shutdown_event():
    global db_pool
    if db_pool:
        db_pool.closeall()
        logger.info("DB Connection Pool closed")

def get_drift_detector():
    """Lazy load drift detector (loads embedding model)."""
    global _drift_detector
    if _drift_detector is None:
        from monitoring.drift_detector import DriftDetector
        _drift_detector = DriftDetector()
        logger.info("Drift detector initialized")
    return _drift_detector

def get_error_classifier():
    """Lazy load error classifier."""
    global _error_classifier
    if _error_classifier is None:
        from monitoring.error_classifier import ErrorClassifier
        _error_classifier = ErrorClassifier()
        logger.info("Error classifier initialized")
    return _error_classifier

def get_ground_truth():
    """Load ground truth into cache for fast lookup."""
    global _ground_truth_cache
    if _ground_truth_cache is None:
        try:
            with open("data/ground_truth/all_queries.json") as f:
                gt_list = json.load(f)
            # Index by normalized query text for lookup
            _ground_truth_cache = {}
            for q in gt_list:
                key = q["query_text"].strip().lower().rstrip("?.!")
                _ground_truth_cache[key] = {
                    "query_id": q["query_id"],
                    "sql": q["sql"],
                    "complexity": q["complexity"],
                    "agent_type": q["agent_type"]
                }
            logger.info(f"Ground truth loaded: {len(_ground_truth_cache)} queries")
        except Exception as e:
            logger.warning(f"Could not load ground truth: {e}")
            _ground_truth_cache = {}
    return _ground_truth_cache

def lookup_ground_truth(query_text: str) -> Optional[Dict]:
    """Find ground truth for a query (exact match on normalized text)."""
    gt = get_ground_truth()
    key = query_text.strip().lower().rstrip("?.!")
    return gt.get(key)

# ── DB helper ────────────────────────────────────────────────────────────────
@contextmanager
def get_db():
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)

# ── Pydantic request models ──────────────────────────────────────────────────
class QueryRequest(BaseModel):
    query:      str
    agent_type: str = Field(..., description="'spend' or 'demand'")

class IngestRequest(BaseModel):
    query_text: str
    agent_type: str
    status: str
    sql: Optional[str] = None
    error: Optional[str] = None
    execution_time_ms: Optional[float] = 0.0

class EvaluateRequest(BaseModel):
    query_id:         str
    query_text:       str
    agent_type:       str
    generated_sql:    str
    ground_truth_sql: str
    complexity:       str = "unknown"

class BaselineUpdateRequest(BaseModel):
    agent_type: str = Field(..., description="'spend' or 'demand'")
    queries:    List[str]

class SqlExecuteRequest(BaseModel):
    sql: str
    agent_type: str

# ── Health ───────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    """Gateway health + downstream agent status."""
    status = {"gateway": "ok", "agents": {}, "automation": "enabled", "auth_enabled": settings.AUTH_ENABLED}
    for name, base in AGENT_URLS.items():
        try:
            r = http.get(f"{base}/health", timeout=3)
            status["agents"][name] = r.json()
        except Exception:
            status["agents"][name] = {"status": "down"}
    return status

# ── Auth info ────────────────────────────────────────────────────────────────
@app.get("/api/v1/auth/me")
async def get_user_info(user: AuthUser = Depends(require_auth)):
    """Get current authenticated user information."""
    return {
        "authenticated": True,
        "sub": user.sub,
        "name": user.name,
        "email": user.email,
        "roles": user.roles,
        "tenant_id": user.tenant_id
    }

@app.get("/api/v1/auth/config")
def get_auth_config():
    """Get Azure AD configuration for frontend (public info only)."""
    return {
        "auth_enabled": settings.AUTH_ENABLED,
        "tenant_id": settings.AZURE_AD_TENANT_ID if settings.AUTH_ENABLED else None,
        "client_id": settings.AZURE_AD_CLIENT_ID if settings.AUTH_ENABLED else None,
        "authority": settings.azure_ad_authority if settings.AUTH_ENABLED else None,
        "scopes": [f"api://{settings.AZURE_AD_CLIENT_ID}/access"] if settings.AUTH_ENABLED else []
    }

# ══════════════════════════════════════════════════════════════════════════════
# ██  AUTOMATED QUERY ENDPOINT                                                ██
# ══════════════════════════════════════════════════════════════════════════════
@app.post("/api/v1/query")
async def route_query(req: QueryRequest, user: Optional[AuthUser] = Depends(get_current_user)):
    """
    AUTOMATED PIPELINE:
    1. Call agent → get SQL + results
    2. Auto drift detection → store in DB
    3. Auto error classification (if error) → store in DB
    4. Auto evaluation (if ground truth exists) → store in DB
    5. Return response with all metrics

    Protected by Azure AD when AUTH_ENABLED=true
    """
    if req.agent_type not in AGENT_URLS:
        raise HTTPException(status_code=400, detail="agent_type must be 'spend' or 'demand'")

    # Generate unique query ID for this request
    query_id = f"LIVE-{req.agent_type.upper()}-{uuid.uuid4().hex[:8]}"

    # Log initial query to DB
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO monitoring.queries (query_id, query_text, agent_type, user_id, status)
                VALUES (%s, %s, %s, %s, 'pending')
            """, (query_id, req.query, req.agent_type, user.sub if user else None))
            conn.commit()
            cur.close()
    except Exception as e:
        logger.error(f"Failed to log query to DB: {e}")

    response = {
        "query_id": query_id,
        "query": req.query,
        "agent_type": req.agent_type,
        "sql": None,
        "results": [],
        "status": "success",
        "error": None,
        # Automated metrics
        "drift": None,
        "error_classification": None,
        "evaluation": None,
        # User info (if authenticated)
        "user": user.name if user else "anonymous"
    }

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 1: Call Agent
    # ─────────────────────────────────────────────────────────────────────────
    base = AGENT_URLS[req.agent_type]
    try:
        agent_resp = http.post(f"{base}/query", json={"query": req.query}, timeout=30)
        agent_resp.raise_for_status()
        agent_data = agent_resp.json()

        response["sql"] = agent_data.get("sql")
        response["results"] = agent_data.get("results", [])
        response["status"] = agent_data.get("status", "success")
        response["error"] = agent_data.get("error")

    except http.exceptions.Timeout:
        response["status"] = "error"
        response["error"] = "Agent timed out"
        # ALERT: Agent timeout (potential system issue)
        alert_service.alert_system_down(
            service=f"{req.agent_type.capitalize()} Agent",
            error="Agent request timed out after 30 seconds"
        )
    except Exception as e:
        response["status"] = "error"
        response["error"] = str(e)
        # ALERT: Agent connection failure
        if "Connection refused" in str(e) or "Connection error" in str(e):
            alert_service.alert_system_down(
                service=f"{req.agent_type.capitalize()} Agent",
                error=str(e)
            )

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 2: Auto Drift Detection (always runs)
    # ─────────────────────────────────────────────────────────────────────────
    try:
        drift_detector = get_drift_detector()
        drift_result = drift_detector.detect(query_id, req.query, req.agent_type)
        response["drift"] = {
            "score": round(drift_result.get("drift_score", 0), 3),
            "classification": drift_result.get("drift_classification", "unknown"),
            "is_anomaly": drift_result.get("anomaly_flag", False)
        }
        logger.info(f"[{query_id}] Drift: {response['drift']['classification']} ({response['drift']['score']})")

        # ALERT: Send email alert for high drift
        if response["drift"]["classification"].lower() == "high":
            alert_service.alert_high_drift(
                query_id=query_id,
                query_text=req.query,
                drift_score=response["drift"]["score"],
                agent_type=req.agent_type
            )
    except Exception as e:
        logger.error(f"Drift detection failed: {e}")
        response["drift"] = {"error": str(e)}

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 3: Auto Error Classification (if error occurred)
    # ─────────────────────────────────────────────────────────────────────────
    if response["status"] == "error" and response["error"]:
        try:
            error_classifier = get_error_classifier()
            error_result = error_classifier.classify(
                query_id=query_id,
                query_text=req.query,
                error_message=response["error"]
            )
            response["error_classification"] = {
                "category": error_result.get("category", "UNKNOWN"),
                "severity": error_result.get("severity", "medium"),
                "suggested_fix": error_result.get("suggested_fix", "")
            }
            logger.info(f"[{query_id}] Error classified: {response['error_classification']['category']}")

            # ALERT: Send email alert for critical errors
            if response["error_classification"]["severity"].lower() == "critical":
                alert_service.alert_critical_error(
                    query_id=query_id,
                    error_category=response["error_classification"]["category"],
                    error_message=response["error"],
                    agent_type=req.agent_type
                )
        except Exception as e:
            logger.error(f"Error classification failed: {e}")
            response["error_classification"] = {"error": str(e)}

    # ─────────────────────────────────────────────────────────────────────────
    # STEP 4: Auto Evaluation (if ground truth exists for this query)
    # ─────────────────────────────────────────────────────────────────────────
    if response["sql"] and response["status"] == "success":
        gt = lookup_ground_truth(req.query)
        if gt:
            try:
                from evaluation.evaluator import Evaluator
                evaluator = Evaluator(req.agent_type)
                eval_result = evaluator.evaluate(
                    query_id=query_id,
                    query_text=req.query,
                    generated_sql=response["sql"],
                    ground_truth_sql=gt["sql"],
                    complexity=gt["complexity"]
                )
                evaluator.store_result(eval_result)

                response["evaluation"] = {
                    "result": eval_result["final_result"],
                    "score": round(eval_result["final_score"], 3),
                    "confidence": round(eval_result["confidence"], 3),
                    "scores": {
                        "structural": round(eval_result["scores"].get("structural", 0), 3),
                        "semantic": round(eval_result["scores"].get("semantic", 0), 3),
                        "llm": round(eval_result["scores"].get("llm", 0), 3)
                    },
                    "ground_truth_id": gt["query_id"]
                }
                logger.info(f"[{query_id}] Evaluation: {response['evaluation']['result']} (score={response['evaluation']['score']})")
            except Exception as e:
                logger.error(f"Evaluation failed: {e}")
                response["evaluation"] = {"error": str(e)}
        else:
            response["evaluation"] = {"status": "skipped", "reason": "no ground truth match"}

    return response



# ─────────────────────────────────────────────────────────────────────────
# NEW: ASYNC TELEMETRY INGEST
# ─────────────────────────────────────────────────────────────────────────

def process_ingest_background(query_id: str, req: IngestRequest):
    """Run heavy monitoring tasks in background to avoid blocking agents."""
    # 2. Drift
    try:
        drift_detector = get_drift_detector()
        drift_detector.detect(query_id, req.query_text, req.agent_type)
    except Exception as e:
        logger.error(f"Drift check failed: {e}")

    # 3. Error
    if req.status == "error" and req.error:
        try:
            error_classifier = get_error_classifier()
            error_classifier.classify(req.error, query_id)
        except Exception as e:
            logger.error(f"Error classify failed: {e}")

    # 4. Evaluation
    if req.sql and req.status == "success":
        gt = lookup_ground_truth(req.query_text)
        if gt:
            try:
                from evaluation.evaluator import Evaluator
                evaluator = Evaluator(req.agent_type)
                eval_result = evaluator.evaluate(
                    query_id=query_id,
                    query_text=req.query_text,
                    generated_sql=req.sql,
                    ground_truth_sql=gt["sql"],
                    complexity=gt["complexity"]
                )
                evaluator.store_result(eval_result)
            except Exception as e:
                logger.error(f"Evaluation failed: {e}")

@app.post("/api/v1/monitor/ingest")
async def ingest_telemetry(req: IngestRequest, background_tasks: BackgroundTasks):
    """Receives async logs from independent agents."""
    query_id = f"ASYNC-{req.agent_type.upper()}-{uuid.uuid4().hex[:8]}"
    logger.info(f"[{query_id}] Ingesting telemetry: {req.query_text}")

    # 1. Log to DB (Sync, must happen now to reserve ID)
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO monitoring.queries (query_id, query_text, agent_type, status, generated_sql)
                VALUES (%s, %s, %s, %s, %s)
            """, (query_id, req.query_text, req.agent_type, req.status, req.sql))
            conn.commit()
            cur.close()
    except Exception as e:
        logger.error(f"DB Insert failed: {e}")

    # Queue heavy tasks
    background_tasks.add_task(process_ingest_background, query_id, req)

    return {"status": "ingested", "query_id": query_id}

# ══════════════════════════════════════════════════════════════════════════════
# ██  MANUAL ENDPOINTS (unchanged)                                            ██
# ══════════════════════════════════════════════════════════════════════════════

# ── POST /api/v1/evaluate ────────────────────────────────────────────────────
@app.post("/api/v1/evaluate")
async def evaluate(req: EvaluateRequest, user: Optional[AuthUser] = Depends(get_current_user)):
    """Run the full 6-step evaluation pipeline manually."""
    from evaluation.evaluator import Evaluator

    evaluator = Evaluator(req.agent_type)
    result    = evaluator.evaluate(
        query_id=req.query_id,
        query_text=req.query_text,
        generated_sql=req.generated_sql,
        ground_truth_sql=req.ground_truth_sql,
        complexity=req.complexity
    )
    evaluator.store_result(result)

    return {
        "query_id":   result["query_id"],
        "result":     result["final_result"],
        "final_score": result["final_score"],
        "confidence": result["confidence"],
        "scores":     result["scores"],
        "reasoning":  result.get("steps", {}).get("llm_judge", {}).get("reasoning", "")
    }

# ── POST /api/v1/debug/execute ──────────────────────────────────────────────
@app.post("/api/v1/debug/execute")
def execute_sql(req: SqlExecuteRequest):
    """Execute SQL for debugging purposes."""
    if not req.sql.strip().upper().startswith("SELECT"):
        raise HTTPException(status_code=400, detail="Only SELECT statements are allowed for debugging.")

    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute(req.sql)
            if cur.description:
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                results = []
                for row in rows[:50]:
                    item = {}
                    for i, col in enumerate(columns):
                        val = row[i]
                        if isinstance(val, (datetime, decimal.Decimal)):
                            val = str(val)
                        item[col] = val
                    results.append(item)
                return {"status": "success", "results": results}
            return {"status": "success", "results": []}
        except Exception as e:
            logger.error(f"Debug execution failed: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            cur.close()

# ── GET /api/v1/metrics ──────────────────────────────────────────────────────
@app.get("/api/v1/metrics")
def get_metrics():
    """Overall + per-agent accuracy metrics from monitoring.evaluations."""
    with get_db() as conn:
        cur  = conn.cursor()

        cur.execute("""
            SELECT COUNT(*),
                   SUM(CASE WHEN result = 'PASS' THEN 1 ELSE 0 END),
                   AVG(final_score)
            FROM monitoring.evaluations
        """)
        total, passed, avg_score = cur.fetchone()
        total  = total  or 0
        passed = passed or 0

        cur.execute("""
            SELECT agent_type,
                   COUNT(*),
                   SUM(CASE WHEN result = 'PASS' THEN 1 ELSE 0 END),
                   AVG(final_score)
            FROM monitoring.evaluations
            GROUP BY agent_type
        """)
        per_agent = {}
        for row in cur.fetchall():
            t, p = row[1], row[2] or 0
            per_agent[row[0]] = {
                "total":    t,
                "passed":   p,
                "accuracy": round(p / t * 100, 1) if t else 0,
                "avg_score": round(float(row[3]), 3) if row[3] else 0.0
            }

        cur.close()

    return {
        "overall": {
            "total_evaluations": total,
            "passed":            passed,
            "failed":            total - passed,
            "accuracy":          round(passed / total * 100, 1) if total else 0,
            "avg_score":         round(float(avg_score or 0), 3)
        },
        "per_agent": per_agent
    }

# ── GET /api/v1/drift ────────────────────────────────────────────────────────
@app.get("/api/v1/drift")
def get_drift(agent_type: Optional[str] = Query(None)):
    """Drift distribution, anomaly count, and top high-drift samples."""
    with get_db() as conn:
        cur  = conn.cursor()

        where, params = "", []
        if agent_type:
            # Match 'LIVE-SPEND...' or 'ASYNC-SPEND...'
            keyword = "SPEND" if agent_type.lower() == "spend" else "DEMAND"
            where  = " WHERE query_id LIKE %s"
            params = [f"%{keyword}%"]

        cur.execute(f"""
            SELECT LOWER(drift_classification), COUNT(*), AVG(drift_score)
            FROM monitoring.drift_monitoring {where}
            GROUP BY LOWER(drift_classification)
            ORDER BY LOWER(drift_classification)
        """, params)
        distribution = {
            row[0]: {"count": row[1], "avg_drift_score": round(float(row[2]), 3)}
            for row in cur.fetchall()
        }

        cur.execute(f"SELECT COUNT(*) FROM monitoring.drift_monitoring WHERE is_anomaly = true {where.replace('WHERE','AND') if where else ''}", params)
        anomalies = cur.fetchone()[0]

        cur.execute(f"""
            SELECT d.query_id, d.drift_score, d.drift_classification, q.query_text, q.generated_sql, q.agent_type
            FROM monitoring.drift_monitoring d
            LEFT JOIN monitoring.queries q ON d.query_id = q.query_id
            WHERE LOWER(d.drift_classification) = 'high' {('AND d.query_id LIKE %s' if agent_type else '')}
            ORDER BY d.drift_score DESC LIMIT 20
        """, params if agent_type else [])
        high_samples = [
            {
                "query_id": r[0], 
                "drift_score": round(float(r[1]), 3), 
                "classification": r[2],
                "query_text": r[3] or "Unknown",
                "sql": r[4] or "Not Available (No Eval)",
                "agent_type": r[5] or "spend"
            }
            for r in cur.fetchall()
        ]

        cur.close()

    return {
        "distribution":      distribution,
        "total_anomalies":   anomalies,
        "high_drift_samples": high_samples
    }

# ── GET /api/v1/errors ───────────────────────────────────────────────────────
@app.get("/api/v1/errors")
def get_errors(category: Optional[str] = Query(None), limit: int = Query(20)):
    """Error summary grouped by category + recent errors list."""
    with get_db() as conn:
        cur  = conn.cursor()

        cur.execute("""
            SELECT error_category, severity, COUNT(*)
            FROM monitoring.errors
            GROUP BY error_category, severity
            ORDER BY error_category
        """)
        categories = {}
        for row in cur.fetchall():
            cat = row[0]
            if cat not in categories:
                categories[cat] = {"count": 0, "severities": {}}
            categories[cat]["count"]            += row[2]
            categories[cat]["severities"][row[1]] = row[2]

        q_sql = """
            SELECT e.query_id, e.error_category, e.error_message, e.severity, q.query_text
            FROM monitoring.errors e
            LEFT JOIN monitoring.queries q ON e.query_id = q.query_id
        """
        params = []
        if category:
            q_sql += " WHERE e.error_category = %s"
            params.append(category)
        q_sql += " ORDER BY e.first_seen DESC LIMIT %s"
        params.append(limit)
        
        cur.execute(q_sql, tuple(params))
        recent = [
            {
                "query_id": r[0], 
                "category": r[1], 
                "message": r[2], 
                "severity": r[3],
                "query_text": r[4] or "Unknown"
            }
            for r in cur.fetchall()
        ]

        cur.close()

    return {
        "total_errors": sum(c["count"] for c in categories.values()),
        "categories":   categories,
        "recent_errors": recent
    }

# ── GET /api/v1/errors/{category} ────────────────────────────────────────────
@app.get("/api/v1/errors/{category}")
def get_errors_by_category(category: str):
    """All errors for a specific category with suggested fixes."""
    with get_db() as conn:
        cur  = conn.cursor()
        cur.execute("""
            SELECT query_id, error_message, severity, suggested_fix, first_seen
            FROM monitoring.errors
            WHERE error_category = %s
            ORDER BY first_seen DESC
        """, (category,))
        errors = [
            {
                "query_id":      r[0],
                "message":       r[1],
                "severity":      r[2],
                "suggested_fix": r[3],
                "first_seen":    str(r[4])
            }
            for r in cur.fetchall()
        ]
        cur.close()
    return {"category": category, "count": len(errors), "errors": errors}

# ── GET /api/v1/history ────────────────────────────────────────────────────
@app.get("/api/v1/history")
def get_history(limit: int = 50):
    """Get history of execution runs with evaluation and error details."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                q.query_text,
                e.result,
                e.confidence,
                r.error_category,
                q.agent_type,
                q.created_at,
                q.query_id,
                d.drift_score,
                d.drift_classification
            FROM monitoring.queries q
            LEFT JOIN monitoring.evaluations e ON q.query_id = e.query_id
            LEFT JOIN monitoring.errors r ON q.query_id = r.query_id
            LEFT JOIN monitoring.drift_monitoring d ON q.query_id = d.query_id
            ORDER BY q.created_at DESC
            LIMIT %s
        """, (limit,))
        
        rows = cur.fetchall()
        cur.close()

    history = []
    for row in rows:
        history.append({
            "prompt": row[0],
            "correctness_verdict": row[1] or "N/A",
            "evaluation_confidence": row[2] if row[2] is not None else 0.0,
            "error_bucket": row[3] or "None",
            "dataset": row[4],
            "timestamp": str(row[5]),
            "query_id": row[6],
            "drift_score": row[7] if row[7] is not None else 0.0,
            "drift_level": row[8] or "N/A"
        })
    return history

# ── POST /api/v1/baseline/update ─────────────────────────────────────────────
@app.post("/api/v1/baseline/update")
def update_baseline(req: BaselineUpdateRequest):
    """Rebuild the drift-detection baseline for one agent."""
    if req.agent_type not in ("spend", "demand"):
        raise HTTPException(status_code=400, detail="agent_type must be 'spend' or 'demand'")

    dd = get_drift_detector()
    result = dd.create_baseline(req.agent_type, req.queries)
    return {"status": "ok", "result": result}


# ── GET /api/v1/alerts ───────────────────────────────────────────────────────
@app.get("/api/v1/alerts")
def get_alerts():
    """Generate active alerts based on drift, accuracy, and errors."""
    alerts = []
    
    with get_db() as conn:
        cur = conn.cursor()

        # 1. EVALUATION ACCURACY CHECK
        # Check last 50 evaluations. If accuracy < 90%, fire alert.
        cur.execute("""
            SELECT AVG(final_score), COUNT(*) 
            FROM (SELECT final_score FROM monitoring.evaluations ORDER BY created_at DESC LIMIT 50) sub
        """)
        row = cur.fetchone()
        avg_score = float(row[0]) if row and row[0] is not None else 1.0
        count = row[1] if row else 0
        
        if count > 5 and avg_score < 0.90:
             alerts.append({
                "id": str(uuid.uuid4()),
                "title": "Evaluation Accuracy Degradation",
                "severity": "warning",
                "message": f"Accuracy dropped to {round(avg_score*100, 1)}% (Threshold: 90%)",
                "reason": f"Based on last {count} evaluations.",
                "timestamp": datetime.now().isoformat()
             })

        # 2. DRIFT CHECK
        # Check for High Drift in last 24h (or last 50 queries)
        # We join with queries to ensure we are looking at recent activity
        cur.execute("""
            SELECT COUNT(*) FROM monitoring.drift_monitoring d
            JOIN monitoring.queries q ON d.query_id = q.query_id
            WHERE d.drift_classification = 'high' 
            AND q.created_at > NOW() - INTERVAL '24 hours'
        """)
        high_drift_count = cur.fetchone()[0]
        
        if high_drift_count > 0:
            alerts.append({
                "id": str(uuid.uuid4()),
                "title": "High Drift Detected",
                "severity": "critical" if high_drift_count > 3 else "warning",
                "message": f"{high_drift_count} High Drift queries detected in last 24h.",
                "reason": "User queries deviate significantly from the baseline.",
                "timestamp": datetime.now().isoformat()
            })

        cur.close()

    return alerts

# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
