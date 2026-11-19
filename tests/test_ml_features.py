import pandas as pd
import pytest

from app.ml.dataset import build_snapshot_dataset
from app.ml.features import ALL_FEATURES, build_customer_features
from app.ml.labels import build_labels

CUTOFF = pd.Timestamp("2026-04-01")


def make_tables():
    customers = pd.DataFrame({
        "id": [1, 2, 3],
        "phone": ["0500000001", "0500000002", "0500000002"],
        "created_at": pd.to_datetime(["2025-01-01", "2025-06-01", "2025-06-01"]),
    })
    deals = pd.DataFrame({
        "id": [10, 11, 12, 13],
        "customer_id": [1, 1, 2, 3],
        "store_id": [1, 1, 1, 1],
        "amount_sar": [500.0, 800.0, 1200.0, 1500.0],
        "status": ["paid", "cancelled", "disputed", "cancelled"],
        "created_at": pd.to_datetime(["2026-01-10", "2026-03-01", "2026-03-05", "2026-04-15"]),
        "closed_at": pd.to_datetime(["2026-01-12", "2026-03-02", "2026-04-20", "2026-04-17"]),
        "is_fraud": [False, False, False, True],
    })
    transactions = pd.DataFrame({"id": [100, 101, 102], "deal_id": [10, 11, 12]})
    payment_events = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "transaction_id": [100, 100, 101, 102],
        "event_type": ["on_time", "late", "missed", "missed"],
        "occurred_at": pd.to_datetime(["2026-01-15", "2026-02-20", "2026-03-20", "2026-05-10"]),
    })
    return {
        "customers": customers,
        "deals": deals,
        "transactions": transactions,
        "payment_events": payment_events,
    }


def test_counts_use_only_the_past():
    feats = build_customer_features(make_tables(), CUTOFF)
    assert feats.loc[1, "n_deals"] == 2
    assert feats.loc[2, "n_deals"] == 1
    assert feats.loc[3, "n_deals"] == 0          # its only deal opens after the cutoff
    assert feats.loc[2, "shared_phone_count"] == 1


def test_outcomes_use_only_deals_closed_before_cutoff():
    feats = build_customer_features(make_tables(), CUTOFF)
    assert feats.loc[1, "cancel_rate"] == pytest.approx(0.5)  # 1 cancelled of 2 closed
    assert feats.loc[2, "dispute_rate"] == 0.0                # dispute closes after cutoff


def test_payment_shares_use_only_past_events():
    feats = build_customer_features(make_tables(), CUTOFF)
    assert feats.loc[1, "n_payment_events"] == 3
    assert feats.loc[1, "trouble_share"] == pytest.approx(2 / 3)  # late + missed
    assert feats.loc[1, "missed_share"] == pytest.approx(1 / 3)
    assert feats.loc[2, "n_payment_events"] == 0                  # its only event is after cutoff


def test_changing_future_rows_does_not_change_features():
    base = build_customer_features(make_tables(), CUTOFF)

    future = make_tables()
    future["payment_events"].loc[future["payment_events"]["id"] == 4, "event_type"] = "on_time"
    future["deals"].loc[future["deals"]["id"] == 13, "amount_sar"] = 99999.0
    future["deals"].loc[future["deals"]["id"] == 12, "closed_at"] = pd.Timestamp("2026-05-01")

    changed = build_customer_features(future, CUTOFF)
    pd.testing.assert_frame_equal(base, changed)


def test_labels_use_only_the_window_after_cutoff():
    labels = build_labels(make_tables(), CUTOFF)
    assert labels.loc[2, "default_label"] == 1   # missed on 2026-05-10, inside the window
    assert labels.loc[1, "default_label"] == 0   # missed on 2026-03-20, before the cutoff
    assert labels.loc[3, "fraud_label"] == 1     # fraud deal opened 2026-04-15
    assert labels.loc[1, "fraud_label"] == 0


def test_cutoff_too_late_is_rejected():
    with pytest.raises(ValueError):
        build_labels(make_tables(), pd.Timestamp("2026-09-01"))


def test_snapshot_dataset_has_all_features_and_no_nulls():
    df = build_snapshot_dataset(make_tables(), cutoffs=[CUTOFF])
    assert set(ALL_FEATURES) <= set(df.columns)
    assert {"default_label", "fraud_label", "snapshot_date", "customer_id"} <= set(df.columns)
    assert df[ALL_FEATURES].isna().sum().sum() == 0
    assert len(df) == 3