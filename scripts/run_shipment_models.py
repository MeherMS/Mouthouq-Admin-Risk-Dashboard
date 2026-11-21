"""Shipment models, fastest working flow.

Features known at dispatch: the customer's shipment history in the window
[dispatch - 120 days, dispatch - 30 days), route distance, and store category.
The 30-day lag keeps outcomes of earlier shipments known.

Models
- Delivery success %: logistic regression. Target: delivered on the first attempt.
- Reason if first attempt fails: multinomial logistic regression, trained on
  first-attempt failures only.
- Expected days: city-pair median of actual delivery time in training data.
  This is an estimate, not a learned model.
- RTO: not modeled. Store-claimed deliveries come from a generator rule, so they
  are excluded from training.

Training: dispatched before 2026-06-01. Test: 2026-06-15 to 2026-08-31.

Run from project root: python -m scripts.run_shipment_models
"""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import text

from app.db import engine
from app.synthetic.shipments import distance_km

MODEL_VERSION = "shipment-lr-v1"
TRAIN_END = pd.Timestamp("2026-06-01")
TEST_START = pd.Timestamp("2026-06-15")
TEST_END = pd.Timestamp("2026-09-01")
HISTORY_DAYS = 90
OUTCOME_LAG_DAYS = 30

NUM_FEATURES = [
    "account_age_days", "shared_phone_count",
    "deals_7d", "deals_30d", "cancels_90d", "distance_km",]
CAT_FEATURES = ["category"]
FEATURES = NUM_FEATURES + CAT_FEATURES

QUERY = """
SELECT s.id AS shipment_id, s.deal_id, d.customer_id, st.category,
       s.origin_city, s.destination_city,
       s.dispatched_at, s.expected_at, s.delivered_at, s.final_status,
       s.failure_reason, s.store_claimed_delivered
FROM shipments s
JOIN deals d ON d.id = s.deal_id
JOIN stores st ON st.id = d.store_id
"""

INSERT_SQL = text("""
    INSERT INTO shipment_predictions
        (shipment_id, delivery_success_pct, expected_days, reason_if_failed,
         reason_prob_pct, model_version, computed_at)
    VALUES
        (:shipment_id, :delivery_success_pct, :expected_days, :reason_if_failed,
         :reason_prob_pct, :model_version, :computed_at)
""")


def load_shipments() -> pd.DataFrame:
    df = pd.read_sql(text(QUERY), engine)
    for col in ["dispatched_at", "expected_at", "delivered_at"]:
        df[col] = pd.to_datetime(df[col], utc=True, format="ISO8601").dt.tz_localize(None)
    df["store_claimed_delivered"] = df["store_claimed_delivered"].astype(bool)
    df["distance_km"] = [distance_km(a, b) for a, b in zip(df["origin_city"], df["destination_city"])]
    df["first_failed"] = df["failure_reason"].notna()
    df["first_success"] = (~df["first_failed"]).astype(int)
    return df


DEALS_QUERY = "SELECT id AS other_deal_id, customer_id, status, created_at, closed_at FROM deals"
CUSTOMERS_QUERY = "SELECT id AS customer_id, phone, created_at FROM customers"


def _utc(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, format="ISO8601").dt.tz_localize(None)


def add_dispatch_features(df: pd.DataFrame) -> pd.DataFrame:
    """Features known at dispatch. Uses only deals created before dispatch and
    cancellations closed before dispatch. The shipment's own deal is excluded."""
    deals = pd.read_sql(text(DEALS_QUERY), engine)
    deals["created_at"] = _utc(deals["created_at"])
    deals["closed_at"] = _utc(deals["closed_at"])

    cur = df[["shipment_id", "deal_id", "customer_id", "dispatched_at"]].rename(
        columns={"dispatched_at": "cur_at"}
    )
    pairs = cur.merge(deals, on="customer_id")
    pairs = pairs[
        (pairs["other_deal_id"] != pairs["deal_id"])
        & (pairs["created_at"] < pairs["cur_at"])
    ]

    pairs["deals_7d"] = (pairs["created_at"] >= pairs["cur_at"] - pd.Timedelta(days=7)).astype(int)
    pairs["deals_30d"] = (pairs["created_at"] >= pairs["cur_at"] - pd.Timedelta(days=30)).astype(int)
    pairs["cancels_90d"] = (
        pairs["status"].eq("cancelled")
        & pairs["closed_at"].notna()
        & (pairs["closed_at"] < pairs["cur_at"])
        & (pairs["closed_at"] >= pairs["cur_at"] - pd.Timedelta(days=90))
    ).astype(int)

    agg = pairs.groupby("shipment_id")[["deals_7d", "deals_30d", "cancels_90d"]].sum()

    cust = pd.read_sql(text(CUSTOMERS_QUERY), engine)
    cust["created_at"] = _utc(cust["created_at"])
    cust["shared_phone_count"] = cust.groupby("phone")["customer_id"].transform("size") - 1

    out = df.merge(
        cust[["customer_id", "created_at", "shared_phone_count"]].rename(
            columns={"created_at": "cust_created"}
        ),
        on="customer_id",
        how="left",
    )
    out["account_age_days"] = (out["dispatched_at"] - out["cust_created"]).dt.total_seconds() / 86400
    out = out.merge(agg, left_on="shipment_id", right_index=True, how="left")
    for col in ["deals_7d", "deals_30d", "cancels_90d"]:
        out[col] = out[col].fillna(0)
    return out

def make_preprocessor() -> ColumnTransformer:
    return ColumnTransformer([
        ("num", StandardScaler(), NUM_FEATURES),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_FEATURES),
    ])


def main() -> None:
    df = add_dispatch_features(load_shipments())
    ordinary = ~df["store_claimed_delivered"]
    train = df[ordinary & (df["dispatched_at"] < TRAIN_END)]
    test = df[ordinary & (df["dispatched_at"] >= TEST_START) & (df["dispatched_at"] < TEST_END)]
    print(f"Train: {len(train)} shipments. Test: {len(test)} shipments.")

    # 1. Delivery success (first attempt)
    delivery = make_pipeline(make_preprocessor(), LogisticRegression(max_iter=1000))
    delivery.fit(train[FEATURES], train["first_success"])
    p_test = delivery.predict_proba(test[FEATURES])[:, 1]
    print("\n== Delivery success (first attempt) ==")
    print(f"ROC-AUC: {roc_auc_score(test['first_success'], p_test):.3f}")
    print(f"Base rate: {test['first_success'].mean():.4f}, mean predicted: {p_test.mean():.4f}")

    # 2. Reason if first attempt fails
    fail_train = train[train["first_failed"]]
    fail_test = test[test["first_failed"]]
    reason = make_pipeline(make_preprocessor(), LogisticRegression(max_iter=1000))
    reason.fit(fail_train[FEATURES], fail_train["failure_reason"])
    majority = fail_train["failure_reason"].value_counts().idxmax()
    pred = reason.predict(fail_test[FEATURES])
    acc = accuracy_score(fail_test["failure_reason"], pred)
    base_acc = accuracy_score(fail_test["failure_reason"], [majority] * len(fail_test))
    print("\n== Reason if first attempt fails ==")
    print(f"Test failures: {len(fail_test)}")
    print(f"Accuracy: {acc:.3f} vs majority class '{majority}': {base_acc:.3f}")

    # 3. Expected days: city-pair median from training deliveries
    done = train[train["delivered_at"].notna()].copy()
    done["actual_days"] = (done["delivered_at"] - done["dispatched_at"]).dt.total_seconds() / 86400
    pair_median = done.groupby(["origin_city", "destination_city"])["actual_days"].median()
    global_median = float(done["actual_days"].median())
    key = pd.MultiIndex.from_frame(df[["origin_city", "destination_city"]])
    expected = pd.Series(pair_median.reindex(key).to_numpy(), index=df.index).fillna(global_median)

    test_done = test[test["delivered_at"].notna()]
    actual = (test_done["delivered_at"] - test_done["dispatched_at"]).dt.total_seconds() / 86400
    promised = (test_done["expected_at"] - test_done["dispatched_at"]).dt.total_seconds() / 86400
    mae_model = float((actual - expected.loc[test_done.index]).abs().mean())
    mae_promised = float((actual - promised).abs().mean())
    print("\n== Expected days (city-pair estimate) ==")
    print(f"MAE vs actual: {mae_model:.2f} days. Promised date MAE: {mae_promised:.2f} days.")

    # 4. Write predictions for every shipment
    p_all = delivery.predict_proba(df[FEATURES])[:, 1]
    reason_proba = reason.predict_proba(df[FEATURES])
    reason_classes = reason.named_steps["logisticregression"].classes_
    top = reason_proba.argmax(axis=1)

    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
    rows = [
        {
            "shipment_id": int(sid),
            "delivery_success_pct": round(float(p_all[i]) * 100, 2),
            "expected_days": round(float(expected.iloc[i]), 2),
            "reason_if_failed": str(reason_classes[top[i]]),
            "reason_prob_pct": round(float(reason_proba[i, top[i]]) * 100, 2),
            "model_version": MODEL_VERSION,
            "computed_at": now,
        }
        for i, sid in enumerate(df["shipment_id"])
    ]

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM shipment_predictions WHERE model_version = :v"),
            {"v": MODEL_VERSION},
        )
        for start in range(0, len(rows), 5000):
            conn.execute(INSERT_SQL, rows[start:start + 5000])
    print(f"\nWrote {len(rows)} shipment predictions, model_version={MODEL_VERSION}")


if __name__ == "__main__":
    main()