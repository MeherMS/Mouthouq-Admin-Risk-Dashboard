"""Population filters for the default model.

fraud_actor_customer_ids uses the generator's synthetic_profile column. That is ground
truth, so results that depend on this filter are diagnostics, not production results.
"""
import pandas as pd


def fraud_actor_customer_ids(engine) -> set[int]:
    df = pd.read_sql(
        "SELECT id FROM customers WHERE synthetic_profile = 'fraud_actor'", engine
    )
    return {int(x) for x in df["id"]}


def drop_customers(df: pd.DataFrame, customer_ids) -> pd.DataFrame:
    """Remove every row whose customer_id is in customer_ids."""
    return df[~df["customer_id"].isin(list(customer_ids))].copy()