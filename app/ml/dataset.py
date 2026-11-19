"""Stack features and labels across cutoffs into one training table."""
import pandas as pd

from app.ml.config import CUTOFFS
from app.ml.features import build_customer_features
from app.ml.labels import build_labels


def build_snapshot_dataset(tables: dict, cutoffs=CUTOFFS) -> pd.DataFrame:
    frames = []
    for cutoff in cutoffs:
        features = build_customer_features(tables, cutoff)
        labels = build_labels(tables, cutoff)
        frame = features.join(labels, how="left")
        frame["snapshot_date"] = pd.Timestamp(cutoff)
        frames.append(frame)
    return pd.concat(frames).reset_index()