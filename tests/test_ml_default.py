import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from app.ml.default_model import (
    MODEL_FEATURES,
    NON_PAYMENT_FEATURES,
    PAYMENT_FEATURES,
    fit_default_model,
    predict_default,
)
from app.ml.features import ALL_FEATURES


def synthetic_frame(n: int = 400, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(rng.normal(size=(n, len(ALL_FEATURES))), columns=ALL_FEATURES)
    df["trouble_share"] = rng.uniform(0, 1, n)
    logit = 3 * df["trouble_share"] - 1.5
    df["default_label"] = (rng.uniform(size=n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df


def test_amount_ratio_recent_is_excluded():
    assert "amount_ratio_recent" not in MODEL_FEATURES
    assert len(MODEL_FEATURES) == len(ALL_FEATURES) - 1


def test_no_labels_or_ids_in_features():
    for col in ["default_label", "fraud_label", "snapshot_date", "customer_id"]:
        assert col not in MODEL_FEATURES


def test_payment_split_is_a_partition():
    assert set(PAYMENT_FEATURES).isdisjoint(NON_PAYMENT_FEATURES)
    assert set(PAYMENT_FEATURES) | set(NON_PAYMENT_FEATURES) == set(MODEL_FEATURES)


def test_probabilities_are_valid_and_informative():
    df = synthetic_frame()
    model = fit_default_model(df.iloc[:300])
    proba = predict_default(model, df.iloc[300:])
    assert proba.min() >= 0.0 and proba.max() <= 1.0
    assert roc_auc_score(df.iloc[300:]["default_label"], proba) > 0.7