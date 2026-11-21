from contextlib import closing
from pathlib import Path
import sqlite3

db_path = Path(
    "C:/Users/meher/Desktop/mouthouq/admin-risk-dashboard/data/risk.db"
)

customer_delivery_stats_sql = """
SELECT
    s.failure_reason,
    s.store_claimed_delivered,
    COUNT(*) AS n,
    SUM(CASE WHEN s.delivered_at IS NOT NULL THEN 1 ELSE 0 END) AS delivered_n,
    SUM(CASE WHEN s.delivered_at IS NOT NULL
              AND julianday(s.delivered_at) <= julianday(s.expected_at)
             THEN 1 ELSE 0 END) AS on_time_n
FROM shipments s
JOIN deals d ON d.id = s.deal_id
WHERE d.customer_id = ?
GROUP BY s.failure_reason, s.store_claimed_delivered;
"""

customer_id = 7370

with closing(sqlite3.connect(db_path)) as conn:
  with conn:
    cursor = conn.cursor()
    cursor.execute(customer_delivery_stats_sql, (customer_id,))
    rows = cursor.fetchall()

for failure_reason, claimed_delivered, n, delivered_n, on_time_n in rows:
  reason_label = failure_reason if failure_reason is not None else "(NULL / None)"
  claimed_label = (
      claimed_delivered if claimed_delivered is not None else "(NULL / None)"
  )
  print(
      f"failure_reason={reason_label} | store_claimed_delivered={claimed_label}"
      f" | n={n} | delivered_n={delivered_n} | on_time_n={on_time_n}"
  )