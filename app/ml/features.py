"""Customer features as they were known on a cutoff date.

Every feature uses only rows that existed before the cutoff. Changing any row
dated on or after the cutoff must not change the output (see tests).
"""
import pandas as pd

from app.ml.config import TROUBLE_EVENTS

ACCOUNT_FEATURES = ["account_age_days", "shared_phone_count"]
ACTIVITY_FEATURES = ["n_deals", "deals_7d", "deals_30d", "deals_90d"]
OUTCOME_FEATURES = ["cancel_rate", "dispute_rate"]
AMOUNT_FEATURES = ["mean_amount", "max_amount", "amount_ratio_recent"]
PAYMENT_FEATURES = [
    "n_payment_events", "trouble_share", "missed_share", "late_share", "trouble_trend",
]
ALL_FEATURES = (
    ACCOUNT_FEATURES + ACTIVITY_FEATURES + OUTCOME_FEATURES
    + AMOUNT_FEATURES + PAYMENT_FEATURES
)


def _fill(s: pd.Series, index: pd.Index) -> pd.Series:
    """Align to customers; customers with no rows get 0."""
    return s.reindex(index).fillna(0.0)


def _ratio(num: pd.Series, den: pd.Series, index: pd.Index) -> pd.Series:
    num = num.reindex(index).fillna(0.0)
    den = den.reindex(index).fillna(0.0)
    return (num / den.where(den > 0)).fillna(0.0)


def build_customer_features(tables: dict, cutoff) -> pd.DataFrame:
    cutoff = pd.Timestamp(cutoff)
    day = pd.Timedelta(days=1)

    # Customers known at the cutoff
    customers = tables["customers"]
    base = (
        customers[customers["created_at"] < cutoff]
        .set_index("id")[["phone", "created_at"]]
        .rename_axis("customer_id")
    )
    feats = pd.DataFrame(index=base.index)

    # Account
    feats["account_age_days"] = (cutoff - base["created_at"]).dt.total_seconds() / 86400
    feats["shared_phone_count"] = base.groupby("phone")["created_at"].transform("size") - 1

    # Deals opened before the cutoff
    deals = tables["deals"]
    past = deals[deals["created_at"] < cutoff]

    # Activity
    feats["n_deals"] = _fill(past.groupby("customer_id").size(), feats.index)
    for days in (7, 30, 90):
        recent = past[past["created_at"] >= cutoff - days * day]
        feats[f"deals_{days}d"] = _fill(recent.groupby("customer_id").size(), feats.index)

    # Outcomes known at the cutoff: deals whose closed_at is before the cutoff
    closed = past[past["closed_at"].notna() & (past["closed_at"] < cutoff)]
    n_closed = closed.groupby("customer_id").size()
    n_cancelled = closed[closed["status"] == "cancelled"].groupby("customer_id").size()
    n_disputed = closed[closed["status"] == "disputed"].groupby("customer_id").size()
    feats["cancel_rate"] = _ratio(n_cancelled, n_closed, feats.index)
    feats["dispute_rate"] = _ratio(n_disputed, n_closed, feats.index)

    # Amounts
    grouped_amount = past.groupby("customer_id")["amount_sar"]
    feats["mean_amount"] = _fill(grouped_amount.mean(), feats.index)
    feats["max_amount"] = _fill(grouped_amount.max(), feats.index)
    recent_mask = past["created_at"] >= cutoff - 90 * day
    recent_mean = past[recent_mask].groupby("customer_id")["amount_sar"].mean()
    earlier_mean = past[~recent_mask].groupby("customer_id")["amount_sar"].mean()
    # Recent 90-day mean over earlier mean. Customers missing either side get 1.0 (neutral).
    feats["amount_ratio_recent"] = (
        (recent_mean / earlier_mean).reindex(feats.index).fillna(1.0)
    )

    # Payments: events dated before the cutoff, on deals opened before the cutoff
    tx_map = tables["transactions"][["id", "deal_id"]].rename(columns={"id": "transaction_id"})
    deal_owner = past[["id", "customer_id"]].rename(columns={"id": "deal_id"})
    pay = tables["payment_events"].merge(tx_map, on="transaction_id").merge(deal_owner, on="deal_id")
    pay = pay[pay["occurred_at"] < cutoff].assign(
        is_trouble=lambda d: d["event_type"].isin(TROUBLE_EVENTS),
        is_missed=lambda d: d["event_type"].eq("missed"),
        is_late=lambda d: d["event_type"].eq("late"),
    )

    grp = pay.groupby("customer_id")
    feats["n_payment_events"] = _fill(grp.size(), feats.index)
    feats["trouble_share"] = _fill(grp["is_trouble"].mean(), feats.index)
    feats["missed_share"] = _fill(grp["is_missed"].mean(), feats.index)
    feats["late_share"] = _fill(grp["is_late"].mean(), feats.index)

    # Trend: trouble share in the last 90 days minus the 90 days before that.
    # Missing either window gives 0.
    recent_pay = pay[pay["occurred_at"] >= cutoff - 90 * day]
    prior_pay = pay[(pay["occurred_at"] < cutoff - 90 * day) & (pay["occurred_at"] >= cutoff - 180 * day)]
    recent_trouble = recent_pay.groupby("customer_id")["is_trouble"].mean().reindex(feats.index)
    prior_trouble = prior_pay.groupby("customer_id")["is_trouble"].mean().reindex(feats.index)
    feats["trouble_trend"] = (recent_trouble - prior_trouble).fillna(0.0)

    return feats[ALL_FEATURES].astype(float)