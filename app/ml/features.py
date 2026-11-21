"""Default-risk features known at a cutoff. Trailing windows only.

Each feature reads only rows that existed before the cutoff:
- deals opened before the cutoff,
- deal outcomes closed before the cutoff,
- payment events dated before the cutoff.

No cumulative counts. They drift across cutoffs (Phase 2, known limits).
"""
import pandas as pd

from app.ml.config import TROUBLE_EVENTS

DAY = pd.Timedelta(days=1)

# Used by the default model.
DEFAULT_FEATURES = [
    "account_age_days",
    "deals_30d",
    "deals_90d",
    "cancel_rate_90d",
    "dispute_rate_90d",
    "mean_amount_90d",
    "amount_ratio_recent",
    "events_90d",
    "trouble_share_90d",
    "missed_share_90d",
    "late_share_90d",
    "trouble_trend",
]

# Computed for ablation only. Not in the default model.
ABLATION_FEATURES = ["shared_phone_count"]

ALL_FEATURES = DEFAULT_FEATURES + ABLATION_FEATURES


def _count(df: pd.DataFrame, index: pd.Index) -> pd.Series:
    return df.groupby("customer_id").size().reindex(index).fillna(0.0)


def _mean(df: pd.DataFrame, column: str, index: pd.Index) -> pd.Series:
    return df.groupby("customer_id")[column].mean().reindex(index).fillna(0.0)


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    return (num / den.where(den > 0)).fillna(0.0)


def build_customer_features(tables: dict, cutoff) -> pd.DataFrame:
    cutoff = pd.Timestamp(cutoff)
    win30 = cutoff - 30 * DAY
    win90 = cutoff - 90 * DAY
    win180 = cutoff - 180 * DAY

    # Customers known at the cutoff
    customers = tables["customers"]
    base = (
        customers.loc[customers["created_at"] < cutoff, ["id", "phone", "created_at"]]
        .set_index("id")
        .rename_axis("customer_id")
    )
    idx = base.index
    feats = pd.DataFrame(index=idx)

    # Account
    feats["account_age_days"] = (cutoff - base["created_at"]).dt.total_seconds() / 86400
    feats["shared_phone_count"] = base.groupby("phone")["created_at"].transform("size") - 1

    # Deals opened before the cutoff
    deals = tables["deals"]
    past = deals[deals["created_at"] < cutoff]
    feats["deals_30d"] = _count(past[past["created_at"] >= win30], idx)
    feats["deals_90d"] = _count(past[past["created_at"] >= win90], idx)

    # Outcomes closed in the 90 days before the cutoff
    closed90 = past[
        past["closed_at"].notna()
        & (past["closed_at"] < cutoff)
        & (past["closed_at"] >= win90)
    ]
    n_closed = _count(closed90, idx)
    n_cancelled = _count(closed90[closed90["status"] == "cancelled"], idx)
    n_disputed = _count(closed90[closed90["status"] == "disputed"], idx)
    feats["cancel_rate_90d"] = _ratio(n_cancelled, n_closed)
    feats["dispute_rate_90d"] = _ratio(n_disputed, n_closed)

    # Amounts: recent 90 days, and recent mean relative to earlier deals
    recent = past[past["created_at"] >= win90]
    earlier = past[past["created_at"] < win90]
    feats["mean_amount_90d"] = _mean(recent, "amount_sar", idx)
    recent_mean = recent.groupby("customer_id")["amount_sar"].mean()
    earlier_mean = earlier.groupby("customer_id")["amount_sar"].mean()
    # Customers missing either side get 1.0 (neutral)
    feats["amount_ratio_recent"] = (recent_mean / earlier_mean).reindex(idx).fillna(1.0)

    # Payment events on deals opened before the cutoff, dated before the cutoff
    owner = past[["id", "customer_id"]].rename(columns={"id": "deal_id"})
    tx_map = tables["transactions"][["id", "deal_id"]].rename(columns={"id": "transaction_id"})
    pay = tables["payment_events"].merge(tx_map, on="transaction_id").merge(owner, on="deal_id")
    pay = pay[pay["occurred_at"] < cutoff].assign(
        is_trouble=lambda d: d["event_type"].isin(TROUBLE_EVENTS),
        is_missed=lambda d: d["event_type"].eq("missed"),
        is_late=lambda d: d["event_type"].eq("late"),
    )

    pay90 = pay[pay["occurred_at"] >= win90]
    pay_prev = pay[(pay["occurred_at"] >= win180) & (pay["occurred_at"] < win90)]
    feats["events_90d"] = _count(pay90, idx)
    feats["trouble_share_90d"] = _mean(pay90, "is_trouble", idx)
    feats["missed_share_90d"] = _mean(pay90, "is_missed", idx)
    feats["late_share_90d"] = _mean(pay90, "is_late", idx)

    # Trend: trouble share in the last 90 days minus the 90 days before. Missing window gives 0.
    trouble_now = pay90.groupby("customer_id")["is_trouble"].mean().reindex(idx)
    trouble_prev = pay_prev.groupby("customer_id")["is_trouble"].mean().reindex(idx)
    feats["trouble_trend"] = (trouble_now - trouble_prev).fillna(0.0)

    return feats[ALL_FEATURES].astype(float)