"""Load the tables the Phase 2 pipeline needs, with timestamps normalized to naive UTC."""
import pandas as pd

QUERIES = {
    "customers": "SELECT id, phone, created_at FROM customers",
    "deals": (
        "SELECT id, customer_id, store_id, amount_sar, status, "
        "created_at, closed_at, is_fraud FROM deals"
    ),
    "transactions": "SELECT id, deal_id FROM transactions",
    "payment_events": "SELECT id, transaction_id, event_type, occurred_at FROM payment_events",
}

DATETIME_COLUMNS = {
    "customers": ["created_at"],
    "deals": ["created_at", "closed_at"],
    "payment_events": ["occurred_at"],
}


def _to_naive_utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True).dt.tz_localize(None)


def load_tables(engine) -> dict[str, pd.DataFrame]:
    tables = {name: pd.read_sql(sql, engine) for name, sql in QUERIES.items()}
    for name, cols in DATETIME_COLUMNS.items():
        for col in cols:
            tables[name][col] = _to_naive_utc(tables[name][col])
    return tables