import json
import requests
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_simulation():
    print("🚀 Starting 200-Query Simulation (Async Architecture)")
    print("Directly hitting Agents (Ports 8001/8002). Telemetry will appear in Monitor (Port 8000).")

    # Load Queries
    with open("data/ground_truth/all_queries.json") as f:
        all_queries = json.load(f)

    spend_queries = [q for q in all_queries if q.get("agent_type") == "spend"]
    demand_queries = [q for q in all_queries if q.get("agent_type") == "demand"]

    print(f"Loaded {len(spend_queries)} unique Spend queries.")
    print(f"Loaded {len(demand_queries)} unique Demand queries.")

    # Expand to 100 each
    def expand_list(lst, target=100):
        if not lst: return []
        res = []
        while len(res) < target:
            res.extend(lst)
        return res[:target]

    target_spend = expand_list(spend_queries, 100)
    target_demand = expand_list(demand_queries, 100)

    print(f"Queued {len(target_spend)} Spend queries.")
    print(f"Queued {len(target_demand)} Demand queries.")

    # Worker Function
    def send_query(query_obj, port):
        url = f"http://localhost:{port}/query"
        payload = {"query": query_obj["query_text"]}
        try:
            start = time.time()
            resp = requests.post(url, json=payload, timeout=30)
            duration = time.time() - start
            return resp.status_code, duration
        except Exception as e:
            return "error", str(e)

    # Execution
    completed = 0
    total = 200
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        
        # Scheduling Spend (Port 8001)
        for q in target_spend:
            futures.append(executor.submit(send_query, q, 8001))
            
        # Scheduling Demand (Port 8002)
        for q in target_demand:
            futures.append(executor.submit(send_query, q, 8002))
            
        print("⚡ Sending queries...")
        for future in as_completed(futures):
            status, duration = future.result()
            completed += 1
            if completed % 10 == 0:
                print(f"[{completed}/{total}] Queries processed.")

    print("✅ Simulation Complete!")
    print("Use the Dashboard (http://localhost:3000) to view the async telemetry.")

if __name__ == "__main__":
    run_simulation()
