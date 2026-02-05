import requests
import time
import random

API_URL = "http://localhost:8000/api/v1/monitor/ingest"

# 1. Normal Queries (Should satisfy Baseline)
normal_queries = [
    "What is the total spend for Marketing?",
    "Show me the top 10 suppliers by spend amount",
    "List all invoices created in May 2023",
    "Calculate the average invoice amount for IT category",
    "Which supplier has the highest spend?"
]

# 2. Drift Queries (Completely different topics)
drift_queries = [
    "What is the weather like in New York today?",
    "Who is the current President of the United States?",
    "Explain the theory of relativity",
    "Write a Python script to sort a list",
    "What is the best recipe for chocolate cake?"
]

def send_telemetry(query, agent="spend"):
    payload = {
        "query_text": query,
        "agent_type": agent,
        "status": "success",  # Assuming success for telemetry purposes
        "sql": "SELECT 1",    # Dummy SQL
        "error": None,
        "execution_time_ms": random.randint(50, 500)
    }
    try:
        response = requests.post(API_URL, json=payload)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Sent: '{query}'")
        else:
            print(f"❌ Failed: {response.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    print("🚀 Starting Drift Simulation...")
    print(f"Target: {API_URL}\n")

    print("--- Phase 1: Sending Normal Queries (Low Drift) ---")
    for q in normal_queries:
        send_telemetry(q)
        time.sleep(1)  # 1s delay

    print("\n--- Phase 2: Sending Out-of-Domain Queries (High Drift) ---")
    for q in drift_queries:
        send_telemetry(q)
        time.sleep(1)

    print("\n✅ Simulation Complete! Check the Dashboard Drift Panel.")
