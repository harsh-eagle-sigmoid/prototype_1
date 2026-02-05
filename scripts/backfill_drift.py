import psycopg2
import sys
import os

# Add root to path so we can import monitoring
sys.path.append(os.getcwd())

from monitoring.drift_detector import DriftDetector

DB_HOST = "localhost"
DB_NAME = "unilever_poc"
DB_USER = "postgres"
DB_PASS = "postgres"

def run():
    print("Initializing DriftDetector...")
    try:
        detector = DriftDetector()
    except Exception as e:
        print(f"Failed to init detector (maybe pgvector missing?): {e}")
        return

    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
        cur = conn.cursor()
        
        print("Finding queries missing from Drift Monitoring...")
        # Only select queries that have text
        cur.execute("""
            SELECT q.query_id, q.query_text, q.agent_type 
            FROM monitoring.queries q 
            LEFT JOIN monitoring.drift_monitoring d ON q.query_id = d.query_id 
            WHERE d.query_id IS NULL AND q.query_text IS NOT NULL
        """)
        rows = cur.fetchall()
        print(f"Found {len(rows)} queries to backfill.")
        
        count = 0
        for q_id, q_text, agent_type in rows:
            try:
                # detect() calculates AND stores result
                detector.detect(q_id, q_text, agent_type or 'spend') 
                count += 1
                if count % 10 == 0:
                    print(f"Processed {count}...")
            except Exception as e:
                print(f"Error processing {q_id}: {e}")

        print(f"Done. Backfilled {count} queries.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

if __name__ == "__main__":
    run()
