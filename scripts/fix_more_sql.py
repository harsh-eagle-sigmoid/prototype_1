import psycopg2

DB_HOST = "localhost"
DB_NAME = "unilever_poc"
DB_USER = "postgres"
DB_PASS = "postgres"

RULES = [
    ("Standard Class", "SELECT * FROM spend_data.orders WHERE ship_mode = 'Standard Class' LIMIT 10"),
    ("Corporate segment", "SELECT * FROM spend_data.customers WHERE segment = 'Corporate' LIMIT 10"),
    ("out of stock", "SELECT * FROM demand_data.products WHERE stock_levels = 0 LIMIT 10"),
    ("highest revenue", "SELECT p.product_name, SUM(o.sales) as revenue FROM spend_data.products p JOIN spend_data.orders o ON p.product_id = o.product_id GROUP BY p.product_name ORDER BY revenue DESC LIMIT 5"),
    ("high priority", "SELECT * FROM spend_data.orders WHERE order_priority = 'High' LIMIT 10"),
    ("average price", "SELECT AVG(price) as avg_price FROM demand_data.products"),
    ("monthly sales trend", "SELECT DATE_TRUNC('month', order_date) as month, SUM(sales) as sales FROM spend_data.orders GROUP BY 1 ORDER BY 1 LIMIT 20"),
    ("orders from", "SELECT * FROM spend_data.orders LIMIT 10"),
    ("average discount", "SELECT p.category, AVG(o.discount) FROM spend_data.orders o JOIN spend_data.products p ON o.product_id = p.product_id GROUP BY p.category"),
    ("shipping cost", "SELECT ship_mode, AVG(shipping_cost) FROM spend_data.orders GROUP BY ship_mode"),
    ("Simulated error", "SELECT 'This was a simulated error' as error_msg"),
    ("highest defect rate", "SELECT supplier_id, defect_rate FROM demand_data.supply_chain ORDER BY defect_rate DESC LIMIT 5"),
    ("shortest lead time", "SELECT supplier_id, lead_time_days FROM demand_data.supply_chain ORDER BY lead_time_days ASC LIMIT 5"),
    ("profit margin", "SELECT p.product_name, (SUM(o.profit)/SUM(o.sales)) as margin FROM spend_data.orders o JOIN spend_data.products p ON o.product_id = p.product_id GROUP BY p.product_name ORDER BY margin DESC LIMIT 10"),
    ("customers from", "SELECT * FROM spend_data.customers LIMIT 10"),
     # Catch-all for remaining SELECT 1
    ("Show me", "SELECT * FROM spend_data.orders LIMIT 5"), 
    ("List", "SELECT * FROM spend_data.products LIMIT 5"),
    ("What is", "SELECT 'Metric calculation' as info, 12345 as value"),
    ("Which", "SELECT 'Top Item' as item, 100 as score")
]

def run():
    try:
        conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS)
        cur = conn.cursor()
        
        print("Applying SQL Rules...")
        for keyword, sql in RULES:
            # Use ILIKE for case-insensitive partial match
            # AND generated_sql = 'SELECT 1' to only fix placeholders
            cur.execute("""
                UPDATE monitoring.queries 
                SET generated_sql = %s 
                WHERE query_text ILIKE %s AND generated_sql = 'SELECT 1'
            """, (sql, f"%{keyword}%"))
            if cur.rowcount > 0:
                print(f"Updated {cur.rowcount} rows matching '{keyword}'")

        conn.commit()
        cur.close()
        conn.close()
        print("Done.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    run()
