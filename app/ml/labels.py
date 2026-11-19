"""Labels for one cutoff: what happened in the HORIZON_DAYS after it.

default_label: a missed payment in the window, on a non-fraud deal opened before the cutoff.
fraud_label:   a fraud deal opened inside the window.
"""
import pandas as pd

from app.ml.config import HORIZON_DAYS, MISSED_EVENT, SIM_END


def check_cutoff(cutoff) -> pd.Timestamp:
    cutoff = pd.Timestamp(cutoff)
    window_end = cutoff + pd.Timedelta(days=HORIZON_DAYS)
    if window_end > SIM_END:
        raise ValueError(
            f"Cutoff {cutoff.date()} gives a label window ending {window_end.date()}, "
            f"after simulation end {SIM_END.date()}."
        )
    return cutoff


def build_labels(tables: dict, cutoff) -> pd.DataFrame:
    cutoff = check_cutoff(cutoff)
    window_end = cutoff + pd.Timedelta(days=HORIZON_DAYS)

    customers = tables["customers"]
    deals = tables["deals"]
    tx = tables["transactions"]
    pe = tables["payment_events"]

    known_ids = pd.Index(
        customers.loc[customers["created_at"] < cutoff, "id"], name="customer_id"
    )
    is_fraud = deals["is_fraud"].astype(bool)

    # Default: missed payment inside the window, on a non-fraud deal opened before the cutoff
    past_normal = deals[(deals["created_at"] < cutoff) & ~is_fraud]
    tx_map = tx[["id", "deal_id"]].rename(columns={"id": "transaction_id"})
    deal_owner = past_normal[["id", "customer_id"]].rename(columns={"id": "deal_id"})
    pay = pe.merge(tx_map, on="transaction_id").merge(deal_owner, on="deal_id")
    in_window = (pay["occurred_at"] >= cutoff) & (pay["occurred_at"] < window_end)
    missed_ids = set(pay.loc[in_window & pay["event_type"].eq(MISSED_EVENT), "customer_id"])

    # Fraud: a fraud deal opened inside the window
    new_fraud = deals[
        is_fraud & (deals["created_at"] >= cutoff) & (deals["created_at"] < window_end)
    ]
    fraud_ids = set(new_fraud["customer_id"])

    labels = pd.DataFrame(index=known_ids)
    labels["default_label"] = labels.index.isin(missed_ids).astype(int)
    labels["fraud_label"] = labels.index.isin(fraud_ids).astype(int)
    return labels