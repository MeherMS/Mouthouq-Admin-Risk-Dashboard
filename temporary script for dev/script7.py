import sqlite3
from pathlib import Path

db_path = Path("../data/risk.db")

if not db_path.exists():
    raise FileNotFoundError(f"Database not found at: {db_path.resolve()}")

query = """
SELECT failure_reason, COUNT(*) FROM transactions GROUP BY failure_reason;
"""

# Using a `with` block commits changes and closes the transaction cleanly
with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    rows = cursor.execute(query).fetchall()

for reason, count in rows:
    print(f"{reason!r}: {count}")