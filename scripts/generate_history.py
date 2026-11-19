import argparse

import pandas as pd
from sqlalchemy import func, select

from app.db import SessionLocal, engine
from app.models import Customer
from app.synthetic.config import FULL, SMALL
from app.synthetic.history import (
    load_db_ids,
    rebuild_population,
    reset_history,
    simulate_history,
)

SUMMARY_QUERIES = {
    "Deals by profile and status": """
        SELECT c.synthetic_profile AS profile, d.status, COUNT(*) AS deals
        FROM deals d JOIN customers c ON c.id = d.customer_id
        GROUP BY c.synthetic_profile, d.status
        ORDER BY c.synthetic_profile, d.status
    """,
    "Deals per customer by profile": """
        SELECT c.synthetic_profile AS profile,
               ROUND(COUNT(d.id) * 1.0 / COUNT(DISTINCT c.id), 1) AS deals_per_customer
        FROM customers c LEFT JOIN deals d ON d.customer_id = c.id
        GROUP BY c.synthetic_profile
    """,
    "Default label rate by profile": """
        SELECT synthetic_profile AS profile,
               COUNT(*) AS customers,
               SUM(CASE WHEN default_label = 1 THEN 1 ELSE 0 END) AS defaulted,
               ROUND(AVG(default_label), 3) AS default_rate
        FROM customers
        GROUP BY synthetic_profile
    """,
    "Fraud deals": """
        SELECT COUNT(*) AS fraud_deals, COUNT(DISTINCT customer_id) AS fraud_customers
        FROM deals WHERE is_fraud = 1
    """,
    "Payment events by profile (non-fraud deals)": """
        SELECT c.synthetic_profile AS profile, e.event_type, COUNT(*) AS events
        FROM payment_events e
        JOIN transactions t ON t.id = e.transaction_id
        JOIN deals d ON d.id = t.deal_id
        JOIN customers c ON c.id = d.customer_id
        WHERE d.is_fraud = 0
        GROUP BY c.synthetic_profile, e.event_type
        ORDER BY c.synthetic_profile, e.event_type
    """,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deals, transactions, payment events and labels.")
    parser.add_argument("--full", action="store_true", help="Use full size (must match the population run).")
    args = parser.parse_args()

    cfg = FULL if args.full else SMALL

    with SessionLocal() as session:
        if not session.scalar(select(func.count()).select_from(Customer)):
            print("No customers found. Run: python -m scripts.generate_population")
            return

        pop_customers, pop_stores = rebuild_population(cfg)
        pop_customers, pop_stores = load_db_ids(session, pop_customers, pop_stores)

        reset_history(session)
        simulate_history(session, cfg, pop_customers, pop_stores)
        session.commit()

    print(f"History generated (seed={cfg.seed}, {'full' if args.full else 'small'} run).")
    for title, sql in SUMMARY_QUERIES.items():
        print(f"\n== {title} ==")
        print(pd.read_sql(sql, engine).to_string(index=False))


if __name__ == "__main__":
    main()