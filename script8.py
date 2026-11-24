from sqlalchemy import text
from app.db import engine

JOIN_SQL = """
SELECT
    s.id                AS shipment_id,
    s.deal_id           AS deal_id,
    s.origin_city       AS origin_city,
    s.destination_city  AS destination_city,
    st.city             AS store_city,
    c.city              AS customer_city
FROM shipments s
LEFT JOIN deals d      ON d.id  = s.deal_id
LEFT JOIN customers c  ON c.id  = d.customer_id
LEFT JOIN stores st    ON st.id = d.store_id
"""

with engine.connect() as conn:
    rows = conn.execute(text(JOIN_SQL)).mappings().all()

total = len(rows)
no_deal = sum(1 for r in rows if r["deal_id"] is None)
no_customer = sum(1 for r in rows if r["deal_id"] is not None and r["customer_city"] is None)
no_store = sum(1 for r in rows if r["deal_id"] is not None and r["store_city"] is None)

print("=== 1. Join coverage ===")
print(f"Shipments total:              {total}")
print(f"Shipments with no deal:       {no_deal}")
print(f"Shipments with no customer:   {no_customer}")
print(f"Shipments with no store:      {no_store}")

usable = [r for r in rows
          if r["customer_city"] is not None and r["store_city"] is not None]

origin_match = sum(1 for r in usable if r["origin_city"] == r["store_city"])
dest_match = sum(1 for r in usable if r["destination_city"] == r["customer_city"])
both_match = sum(1 for r in usable
                 if r["origin_city"] == r["store_city"]
                 and r["destination_city"] == r["customer_city"])

print("\n=== 2. Match rates (shipments with a full join) ===")
print(f"Checked:                      {len(usable)}")
print(f"Origin == store city:         {origin_match} ({origin_match / len(usable):.2%})")
print(f"Destination == customer city: {dest_match} ({dest_match / len(usable):.2%})")
print(f"Both match:                   {both_match} ({both_match / len(usable):.2%})")

print("\n=== 3. Origin mismatches: origin_city vs store city (top 15 pairs) ===")
from collections import Counter
origin_pairs = Counter(
    (r["origin_city"], r["store_city"])
    for r in usable if r["origin_city"] != r["store_city"]
)
if not origin_pairs:
    print("None")
for (o, s), n in origin_pairs.most_common(15):
    print(f"   shipment origin {o!r}, store city {s!r}: {n}")

print("\n=== 4. Destination mismatches: destination_city vs customer city (top 15 pairs) ===")
dest_pairs = Counter(
    (r["destination_city"], r["customer_city"])
    for r in usable if r["destination_city"] != r["customer_city"]
)
if not dest_pairs:
    print("None")
for (d, c), n in dest_pairs.most_common(15):
    print(f"   shipment destination {d!r}, customer city {c!r}: {n}")

print("\n=== 5. Five sample mismatched rows ===")
mismatched = [r for r in usable
              if r["origin_city"] != r["store_city"]
              or r["destination_city"] != r["customer_city"]]
if not mismatched:
    print("None")
for r in mismatched[:5]:
    print(dict(r))