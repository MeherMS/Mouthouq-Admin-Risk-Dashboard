"""Time-based train/test split with a purge gap.

A training row's label covers HORIZON_DAYS after its cutoff. That window must end
before the test cutoff, or training labels would contain test-period events.
"""
import pandas as pd

from app.ml.config import HORIZON_DAYS

TRAIN_CUTOFFS = [pd.Timestamp(d) for d in ["2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01"]]
PURGED_CUTOFFS = [pd.Timestamp(d) for d in ["2026-06-01", "2026-07-01"]]
TEST_CUTOFF = pd.Timestamp("2026-08-01")


def check_no_label_overlap(train_cutoffs, test_cutoff) -> None:
    test_cutoff = pd.Timestamp(test_cutoff)
    for c in train_cutoffs:
        label_end = pd.Timestamp(c) + pd.Timedelta(days=HORIZON_DAYS)
        if label_end > test_cutoff:
            raise ValueError(
                f"Training cutoff {pd.Timestamp(c).date()} has a label window ending "
                f"{label_end.date()}, after test cutoff {test_cutoff.date()}."
            )
        if pd.Timestamp(c) >= test_cutoff:
            raise ValueError(f"Training cutoff {pd.Timestamp(c).date()} is not before the test cutoff.")


def split_by_time(dataset: pd.DataFrame, train_cutoffs=TRAIN_CUTOFFS, test_cutoff=TEST_CUTOFF):
    check_no_label_overlap(train_cutoffs, test_cutoff)
    train = dataset[dataset["snapshot_date"].isin(train_cutoffs)].copy()
    test = dataset[dataset["snapshot_date"] == pd.Timestamp(test_cutoff)].copy()
    return train, test