"""
scripts/run_scoring.py

Phase 2 scoring engine (prototype).
- Default risk: logistic regression on 90-day trailing features.
  Trained on cutoffs Feb-May 2026, tested on the 2026-08-01 cutoff.
- Fraud risk: rule-based score (shared phone, cancellations).
- Scores every customer as of the end of the simulation and writes to risk_scores.

Run from project root:  python -m scripts.run_scoring
"""
import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text

from app.db import engine

MODEL_VERSION = "lr-default-v1+rules-fraud-v1"
SIM_END = datetime(2026, 11, 15)
HORIZON_DAYS = 90
TRAIN_CUTOFFS = [datetime(2026, m, 1) for m in (2, 3, 4, 5)]
TEST_CUTOFF = datetime(2026, 8, 1)
SCORE_CUTOFF = SIM_END

FEATURES = [
    "account_age_days",
    "deals_30d",
    "deals_90d",
    "cancels_90d",
    "late_share_90d",
    "partial_share_90d",
    "missed_share_90d",
    "log_mean_amount_90d",
]


def band(score):
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


# ---------- Load ----------

def read_table(name):
    return pd.read_sql(text(f"SELECT * FROM {name}"), engine)


def to_naive_utc(series):
    return pd.to_datetime(series, utc=True).dt.tz_localize(None)


def load_tables():
    customers = read_table("customers")
    deals = read_table("deals")
    transactions = read_table("transactions")
    events = read_table("payment_events")

    customers["created_at"] = to_naive_utc(customers["created_at"])
    deals["created_at"] = to_naive_utc(deals["created_at"])
    deals["closed_at"] = to_naive_utc(deals["closed_at"])
    events["occurred_at"] = to_naive_utc(events["occurred_at"])
    deals["is_fraud"] = deals["is_fraud"].astype(bool)

    # One row per payment event, with its customer and fraud flag attached
    ev = (
        events[["transaction_id", "event_type", "occurred_at"]]
        .merge(
            transactions[["id", "deal_id"]].rename(columns={"id": "transaction_id"}),
            on="transaction_id",
        )
        .merge(
            deals[["id", "customer_id", "is_fraud"]].rename(columns={"id": "deal_id"}),
            on="deal_id",
        )
    )
    return customers, deals, ev


# ---------- Features (only data before the cutoff) ----------

def build_features(customers, deals, ev, cutoff):
    start90 = cutoff - timedelta(days=90)
    start30 = cutoff - timedelta(days=30)

    cust = customers[customers["created_at"] < cutoff].copy()
    cust["shared_phone_count"] = cust["phone"].map(customers["phone"].value_counts())
    cust = cust.set_index("id")

    feats = cust[["shared_phone_count"]].copy()
    feats["account_age_days"] = (cutoff - cust["created_at"]).dt.days

    past = deals[deals["created_at"] < cutoff]
    d30 = past[past["created_at"] >= start30]
    d90 = past[past["created_at"] >= start90]
    cancels = deals[
        (deals["status"] == "cancelled")
        & (deals["closed_at"] < cutoff)
        & (deals["closed_at"] >= start90)
    ]

    feats["deals_30d"] = d30.groupby("customer_id").size()
    feats["deals_90d"] = d90.groupby("customer_id").size()
    feats["cancels_90d"] = cancels.groupby("customer_id").size()
    feats["mean_amount_90d"] = d90.groupby("customer_id")["amount_sar"].mean()

    e = ev[(ev["occurred_at"] < cutoff) & (ev["occurred_at"] >= start90)]
    total = e.groupby("customer_id").size()
    for kind in ["late", "partial", "missed"]:
        count = e[e["event_type"] == kind].groupby("customer_id").size()
        feats[f"{kind}_share_90d"] = count / total

    feats = feats.fillna(0)
    feats["log_mean_amount_90d"] = np.log1p(feats["mean_amount_90d"])
    return feats[FEATURES + ["shared_phone_count"]]


# ---------- Labels (outcomes after the cutoff, within 90 days) ----------

def build_labels(ev, cutoff, customer_ids):
    end = cutoff + timedelta(days=HORIZON_DAYS)
    assert end <= SIM_END, f"label window for {cutoff.date()} runs past simulation end"
    missed = ev[
        (ev["event_type"] == "missed")
        & (ev["occurred_at"] >= cutoff)
        & (ev["occurred_at"] < end)
        & (~ev["is_fraud"])
    ]
    defaulted = list(set(missed["customer_id"]))
    return pd.Series(customer_ids.isin(defaulted).astype(int), index=customer_ids)


def make_dataset(customers, deals, ev, cutoffs):
    frames = []
    for c in cutoffs:
        X = build_features(customers, deals, ev, c)
        y = build_labels(ev, c, X.index)
        frames.append(X.assign(label=y, cutoff=c))
    return pd.concat(frames)


# ---------- Models ----------

def train_default(train):
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    model.fit(train[FEATURES], train["label"])
    return model


def default_scores(model, X):
    """Returns {customer_id: (score 0-100, top factors)}. Top factors are log-odds contributions."""
    prob = model.predict_proba(X[FEATURES])[:, 1]
    scaler = model.named_steps["standardscaler"]
    coef = model.named_steps["logisticregression"].coef_[0]
    contrib = scaler.transform(X[FEATURES]) * coef

    out = {}
    for i, cid in enumerate(X.index):
        order = np.argsort(-contrib[i])[:3]
        factors = [
            {"factor": FEATURES[j], "log_odds_contribution": round(float(contrib[i, j]), 3)}
            for j in order
            if contrib[i, j] > 0
        ]
        out[int(cid)] = (round(float(prob[i]) * 100, 1), factors)
    return out


def fraud_scores(X):
    """Returns {customer_id: (score 0-100, triggered rules)}."""
    out = {}
    for cid, r in X.iterrows():
        score = 0
        factors = []
        if r["shared_phone_count"] >= 2:
            score += 60
            factors.append({
                "factor": "shared_phone",
                "detail": f"phone shared by {int(r['shared_phone_count'])} accounts",
                "points": 60,
            })
        if r["cancels_90d"] >= 2:
            score += 40
            factors.append({
                "factor": "cancellations",
                "detail": f"{int(r['cancels_90d'])} cancelled deals in 90 days",
                "points": 40,
            })
        out[int(cid)] = (min(score, 100), factors)
    return out


# ---------- Main ----------

def main():
    customers, deals, ev = load_tables()

    train = make_dataset(customers, deals, ev, TRAIN_CUTOFFS)
    test = make_dataset(customers, deals, ev, [TEST_CUTOFF])
    print(f"Train rows: {len(train)}, default positives: {int(train['label'].sum())}")

    model = train_default(train)
    p_test = model.predict_proba(test[FEATURES])[:, 1]
    print(f"Test ROC-AUC (default): {roc_auc_score(test['label'], p_test):.3f}")
    print(f"Test default base rate: {test['label'].mean():.4f}")

    X = build_features(customers, deals, ev, SCORE_CUTOFF)
    d_map = default_scores(model, X)
    f_map = fraud_scores(X)

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
    rows = []
    for cid in X.index:
        cid = int(cid)
        d_score, d_factors = d_map[cid]
        f_score, f_factors = f_map[cid]
        rows.append({
            "entity_type": "customer",
            "entity_id": cid,
            "fraud_score": f_score,
            "default_score": d_score,
            "fraud_band": band(f_score),
            "default_band": band(d_score),
            "model_version": MODEL_VERSION,
            "computed_at": now,
            "top_factors": json.dumps({"default": d_factors, "fraud": f_factors}),
        })

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO risk_scores
                    (entity_type, entity_id, fraud_score, default_score, fraud_band,
                     default_band, model_version, computed_at, top_factors)
                VALUES
                    (:entity_type, :entity_id, :fraud_score, :default_score, :fraud_band,
                     :default_band, :model_version, :computed_at, :top_factors)
            """),
            rows,
        )

    summary = pd.DataFrame(rows)
    print("\nDefault band counts:")
    print(summary["default_band"].value_counts().to_string())
    print("\nFraud band counts:")
    print(summary["fraud_band"].value_counts().to_string())
    print(f"\nWrote {len(rows)} customer scores, model_version={MODEL_VERSION}")


if __name__ == "__main__":
    main()