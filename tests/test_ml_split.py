import pandas as pd
import pytest

from app.ml.baselines import rule_fraud_score
from app.ml.split import TEST_CUTOFF, TRAIN_CUTOFFS, split_by_time

ALL = pd.to_datetime(["2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01",
                      "2026-06-01", "2026-07-01", "2026-08-01"])


def test_split_uses_train_cutoffs_and_test_cutoff():
    ds = pd.DataFrame({"snapshot_date": ALL, "customer_id": range(len(ALL))})
    train, test = split_by_time(ds)
    assert set(train["snapshot_date"]) == set(TRAIN_CUTOFFS)
    assert set(test["snapshot_date"]) == {TEST_CUTOFF}
    assert not (train["snapshot_date"] >= TEST_CUTOFF).any()


def test_overlapping_training_cutoff_is_rejected():
    ds = pd.DataFrame({"snapshot_date": ALL, "customer_id": range(len(ALL))})
    with pytest.raises(ValueError):
        split_by_time(ds, train_cutoffs=TRAIN_CUTOFFS + [pd.Timestamp("2026-06-01")])


def test_rule_score_points():
    df = pd.DataFrame([
        {"shared_phone_count": 0, "account_age_days": 500, "deals_30d": 0,
         "n_deals": 0, "cancel_rate": 0.0, "dispute_rate": 0.0},
        {"shared_phone_count": 1, "account_age_days": 500, "deals_30d": 0,
         "n_deals": 0, "cancel_rate": 0.0, "dispute_rate": 0.0},
        {"shared_phone_count": 1, "account_age_days": 50, "deals_30d": 3,
         "n_deals": 4, "cancel_rate": 0.5, "dispute_rate": 0.5},
    ])
    assert rule_fraud_score(df).tolist() == [0.0, 25.0, 100.0]