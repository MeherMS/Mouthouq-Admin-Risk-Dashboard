"""Signal check for shipment targets. Read-only: writes nothing to the database.

Checks whether the shipment targets separate groups before any model is trained:
1. First-attempt failure and RTO by customer profile (delivery success signal).
2. RTO split by the fake-delivery rule (store_claimed_delivered + rto).
3. First-attempt failure reasons by customer profile.
4. ETA: promised date vs city-pair median baseline, time-based split.

synthetic_profile is generator ground truth. It is used here only to check that
targets separate groups. It is never a model feature.

Run from project root: python -m scripts.signal_check_shipments
"""
import pandas as pd
from sqlalchemy import text

from app.db import engine

SIGNAL_RATIO = 2.0        # fraud vs healthy first-attempt failure rate must differ by this factor
MIN_ORDINARY_RTO = 100    # ordinary RTO count needed for a usable RTO target
REASON_GAP = 0.10         # address_not_found share gap (fraud vs healthy) needed to call a signal
ETA_TRAIN_FRACTION = 0.5  # earliest half of dispatches trains the baseline, latest half tests it
ETA_MIN_GAIN = 0.10       # city-pair baseline must cut MAE vs the promised date by at least 10%

QUERY = """
SELECT s.id AS shipment_id,
       s.origin_city,
       s.destination_city,
       s.dispatched_at,
       s.expected_at,
       s.delivered_at,
       s.attempts,
       s.final_status,
       s.failure_reason,
       s.store_claimed_delivered,
       c.synthetic_profile
FROM shipments s
JOIN deals d ON d.id = s.deal_id
JOIN customers c ON c.id = d.customer_id
"""


def load() -> pd.DataFrame:
    df = pd.read_sql(text(QUERY), engine)
    for col in ["dispatched_at", "expected_at", "delivered_at"]:
        df[col] = pd.to_datetime(df[col], utc=True, format="ISO8601").dt.tz_localize(None)
    df["fake_claim"] = df["store_claimed_delivered"].astype(bool)
    df["is_rto"] = df["final_status"].eq("rto")
    # Fake-delivery RTO: the generator's store-side rule. Only these rows are excluded
    # from the ordinary views. Disputed fraud shipments (claimed, delivered) are kept.
    df["fake_rto"] = df["fake_claim"] & df["is_rto"]
    df["first_attempt_failed"] = df["failure_reason"].notna()
    return df


def summarize_delivery(d: pd.DataFrame) -> pd.DataFrame:
    return d.groupby("synthetic_profile").agg(
        shipments=("shipment_id", "size"),
        first_attempt_fail_rate=("first_attempt_failed", "mean"),
        rto_count=("is_rto", "sum"),
    ).round(4)


def check_delivery(df: pd.DataFrame) -> float:
    print("\n== 1. First-attempt failure and RTO by customer profile ==")
    print("All shipments:")
    print(summarize_delivery(df).to_string())

    ordinary = df[~df["fake_rto"]]
    print("\nExcluding fake-delivery RTOs:")
    t = summarize_delivery(ordinary)
    print(t.to_string())

    rates = t.reindex(index=["fraud_actor", "healthy"], fill_value=0)["first_attempt_fail_rate"]
    healthy = rates.loc["healthy"]
    ratio = float(rates.loc["fraud_actor"] / healthy) if healthy > 0 else float("nan")
    print(f"\nFraud / healthy first-attempt failure ratio: {ratio:.2f}")
    return ratio


def check_rto_split(df: pd.DataFrame) -> int:
    print("\n== 2. RTO by fake-delivery flag ==")
    print(pd.crosstab(df["fake_claim"], df["final_status"], margins=True).to_string())
    ordinary_rto = int((df["is_rto"] & ~df["fake_claim"]).sum())
    print(f"Ordinary RTO (excluding fake-delivery): {ordinary_rto}")
    return ordinary_rto


def check_reasons(df: pd.DataFrame) -> float:
    print("\n== 3. First-attempt failure reason by profile (ordinary shipments) ==")
    failed = df[df["first_attempt_failed"] & ~df["fake_rto"]]
    print("Counts:")
    print(pd.crosstab(failed["synthetic_profile"], failed["failure_reason"]).to_string())
    shares = pd.crosstab(failed["synthetic_profile"], failed["failure_reason"], normalize="index")
    print("\nShares:")
    print(shares.round(3).to_string())
    s = shares.reindex(index=["fraud_actor", "healthy"], columns=["address_not_found"], fill_value=0)
    gap = float(s.loc["fraud_actor", "address_not_found"] - s.loc["healthy", "address_not_found"])
    print(f"\naddress_not_found share gap (fraud minus healthy): {gap:+.3f}")
    return gap


def check_eta(df: pd.DataFrame) -> dict:
    print("\n== 4. ETA: promised date and city-pair baseline (delivered shipments) ==")
    d = df[df["delivered_at"].notna()].sort_values("dispatched_at").copy()
    d["actual_days"] = (d["delivered_at"] - d["dispatched_at"]).dt.total_seconds() / 86400
    d["promised_days"] = (d["expected_at"] - d["dispatched_at"]).dt.total_seconds() / 86400

    cut = int(len(d) * ETA_TRAIN_FRACTION)
    train, test = d.iloc[:cut], d.iloc[cut:].copy()
    print(f"Train: {len(train)} shipments up to {train['dispatched_at'].max().date()}")
    print(f"Test:  {len(test)} shipments from {test['dispatched_at'].min().date()}")

    pair_median = train.groupby(["origin_city", "destination_city"])["actual_days"].median()
    global_median = float(train["actual_days"].median())
    key = pd.MultiIndex.from_frame(test[["origin_city", "destination_city"]])
    pred_pair = pd.Series(pair_median.reindex(key).to_numpy(), index=test.index).fillna(global_median)

    result = {
        "mae_global_median": float((test["actual_days"] - global_median).abs().mean()),
        "mae_pair_median": float((test["actual_days"] - pred_pair).abs().mean()),
        "mae_promised": float((test["actual_days"] - test["promised_days"]).abs().mean()),
        "late_vs_promised": float((test["actual_days"] > test["promised_days"]).mean()),
    }
    print(f"MAE, global median baseline: {result['mae_global_median']:.2f} days")
    print(f"MAE, city-pair median baseline: {result['mae_pair_median']:.2f} days")
    print(f"MAE, promised date: {result['mae_promised']:.2f} days")
    print(f"Share delivered after promised date (test): {result['late_vs_promised']:.3f}")
    return result


def verdict(label: str, ok: bool, detail: str) -> None:
    print(f"{'PASS' if ok else 'WARN'}  {label}: {detail}")


def main() -> None:
    df = load()
    print(f"Shipments loaded: {len(df)}")
    print(f"Fake-delivery RTOs: {int(df['fake_rto'].sum())}")

    ratio = check_delivery(df)
    ordinary_rto = check_rto_split(df)
    gap = check_reasons(df)
    eta = check_eta(df)

    print("\n== Signal summary ==")
    verdict(
        "Delivery failure by profile",
        ratio >= SIGNAL_RATIO,
        f"fraud/healthy ratio {ratio:.2f} (need at least {SIGNAL_RATIO})",
    )
    verdict(
        "Ordinary RTO count",
        ordinary_rto >= MIN_ORDINARY_RTO,
        f"{ordinary_rto} ordinary RTOs (need at least {MIN_ORDINARY_RTO})",
    )
    verdict(
        "Failure reason by profile",
        abs(gap) >= REASON_GAP,
        f"address_not_found gap {gap:+.3f} (need at least {REASON_GAP:.2f} in either direction)",
    )
    verdict(
        "ETA: city-pair baseline beats promised date",
        eta["mae_pair_median"] <= (1 - ETA_MIN_GAIN) * eta["mae_promised"],
        f"{eta['mae_pair_median']:.2f} vs promised {eta['mae_promised']:.2f} days "
        f"(need at least {ETA_MIN_GAIN:.0%} gain)",
    )
    print(
        "\nPASS on these checks means the generator separates the groups. "
        "It does not mean the models will work on real shipments."
    )


if __name__ == "__main__":
    main()