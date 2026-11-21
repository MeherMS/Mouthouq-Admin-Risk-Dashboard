"""Batch scoring for customers, as of the simulation end.

Default risk: logistic regression on DEFAULT_FEATURES, trained in-process on the
Feb to May 2026 cutoffs (same code as app.ml.train). The stored default_score is a
percentile rank across scored customers (0 to 100), not a probability.
Default bands are percentile-based: High = top 1%, Medium = next 9%, Low = rest.

Fraud risk: Phase 2 rules, unchanged.
  - Phone held by at least one other account: 60 points.
  - Two or more cancelled deals closed in the 90 days before the scoring date: 40 points.
  Absolute bands: Low 0 to 39, Medium 40 to 69, High 70 to 100.

Re-running replaces rows with the same model_version. Rows from other versions
are kept as score history.

Run from project root: python -m scripts.run_scoring
"""
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.db import engine
from app.ml.config import SIM_END
from app.ml.data import load_tables
from app.ml.features import DEFAULT_FEATURES, build_customer_features
from app.ml.train import TRAIN_CUTOFFS, build_dataset, fit

MODEL_VERSION = "lr-default-v2-trailing+rules-fraud-v1"

REVIEW_HIGH_FRACTION = 0.01
REVIEW_MEDIUM_FRACTION = 0.10
FRAUD_HIGH, FRAUD_MEDIUM = 70, 40
PHONE_POINTS, CANCEL_POINTS = 60, 40
CANCEL_LOOKBACK_DAYS = 90
TOP_N_FACTORS = 3

INSERT_SQL = text("""
    INSERT INTO risk_scores
        (entity_type, entity_id, fraud_score, default_score, fraud_band,
         default_band, model_version, computed_at, top_factors)
    VALUES
        (:entity_type, :entity_id, :fraud_score, :default_score, :fraud_band,
         :default_band, :model_version, :computed_at, :top_factors)
""")


def cancel_counts(tables: dict, cutoff: pd.Timestamp, index: pd.Index) -> pd.Series:
    """Cancelled deals closed in the lookback window before the cutoff (Phase 2 rule)."""
    start = cutoff - pd.Timedelta(days=CANCEL_LOOKBACK_DAYS)
    deals = tables["deals"]
    closed = deals[
        (deals["status"] == "cancelled")
        & deals["closed_at"].notna()
        & (deals["closed_at"] < cutoff)
        & (deals["closed_at"] >= start)
    ]
    return closed.groupby("customer_id").size().reindex(index).fillna(0).astype(int)


def fraud_band(scores: pd.Series) -> np.ndarray:
    return np.select([scores >= FRAUD_HIGH, scores >= FRAUD_MEDIUM], ["high", "medium"], "low")


def main() -> None:
    cutoff = pd.Timestamp(SIM_END)
    tables = load_tables(engine)

    # Default model, trained on the same cutoffs and features as app.ml.train
    train = build_dataset(tables, TRAIN_CUTOFFS)
    model = fit(train, DEFAULT_FEATURES)
    scaler = model.named_steps["standardscaler"]
    coef = model.named_steps["logisticregression"].coef_[0]

    X = build_customer_features(tables, cutoff)
    ids = X.index
    n = len(ids)
    Xd = X[DEFAULT_FEATURES]
    prob = model.predict_proba(Xd)[:, 1]
    contrib = scaler.transform(Xd) * coef  # log-odds contribution per feature

    # Default: percentile rank and percentile bands
    rank_from_top = pd.Series(prob, index=ids).rank(method="first", ascending=False).astype(int)
    default_score = (100 * (n - rank_from_top + 1) / n).round(2)
    k_high = int(np.ceil(n * REVIEW_HIGH_FRACTION))
    k_medium = int(np.ceil(n * REVIEW_MEDIUM_FRACTION))
    default_band = pd.Series(
        np.where(rank_from_top <= k_high, "high",
                 np.where(rank_from_top <= k_medium, "medium", "low")),
        index=ids,
    )

    # Fraud: Phase 2 rules
    phone_accounts = (X["shared_phone_count"] + 1).round().astype(int)  # includes this account
    cancels = cancel_counts(tables, cutoff, ids)
    fraud_score = (
        PHONE_POINTS * (phone_accounts >= 2).astype(int)
        + CANCEL_POINTS * (cancels >= 2).astype(int)
    ).clip(upper=100)
    fraud_bands = pd.Series(fraud_band(fraud_score), index=ids)

    # Assemble rows
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
    contrib_vals = np.asarray(contrib)
    raw_vals = Xd.to_numpy()
    phone_vals = phone_accounts.to_numpy()
    cancel_vals = cancels.to_numpy()

    rows = []
    for i, cid in enumerate(ids):
        order = np.argsort(-contrib_vals[i])[:TOP_N_FACTORS]
        default_factors = [
            {
                "factor": DEFAULT_FEATURES[j],
                "value": round(float(raw_vals[i, j]), 3),
                "log_odds_contribution": round(float(contrib_vals[i, j]), 3),
            }
            for j in order
            if contrib_vals[i, j] > 0
        ]

        fraud_factors = []
        if phone_vals[i] >= 2:
            fraud_factors.append({
                "factor": "shared_phone",
                "detail": f"phone held by {int(phone_vals[i])} accounts",
                "points": PHONE_POINTS,
            })
        if cancel_vals[i] >= 2:
            fraud_factors.append({
                "factor": "cancellations",
                "detail": f"{int(cancel_vals[i])} cancelled deals in 90 days",
                "points": CANCEL_POINTS,
            })

        rows.append({
            "entity_type": "customer",
            "entity_id": int(cid),
            "fraud_score": float(fraud_score.loc[cid]),
            "default_score": float(default_score.loc[cid]),
            "fraud_band": str(fraud_bands.loc[cid]),
            "default_band": str(default_band.loc[cid]),
            "model_version": MODEL_VERSION,
            "computed_at": now,
            "top_factors": json.dumps({
                "default": default_factors,
                "fraud": fraud_factors,
                "model_output": {
                    "uncalibrated_probability": round(float(prob[i]), 5),
                    "note": "Not calibrated. Use default_score (percentile) for ranking.",
                },
            }),
        })

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM risk_scores WHERE entity_type = 'customer' AND model_version = :v"),
            {"v": MODEL_VERSION},
        )
        conn.execute(INSERT_SQL, rows)

    # Summary for checking
    summary = pd.DataFrame(rows)
    print(f"Scored {n} customers, model_version={MODEL_VERSION}")
    print(f"\nDefault bands (expect 100 high, 900 medium):")
    print(summary["default_band"].value_counts().to_string())
    print(f"\nFraud bands (expect 9379 low, 601 medium, 20 high, same as v1):")
    print(summary["fraud_band"].value_counts().to_string())
    print(f"\nDefault score range: {summary['default_score'].min()} to {summary['default_score'].max()}")
    print("\nTop default factor for high-band customers:")
    top_first = summary.loc[summary["default_band"] == "high", "top_factors"].map(
        lambda s: (json.loads(s)["default"] or [{"factor": "none"}])[0]["factor"]
    )
    print(top_first.value_counts().to_string())


if __name__ == "__main__":
    main()