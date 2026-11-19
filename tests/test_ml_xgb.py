import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from app.ml.default_model import MODEL_FEATURES
from app.ml.features import ALL_FEATURES
from app.ml.xgb_model import XGB_PARAMS, fit_xgb_default, predict_xgb


def synthetic_frame(n: int = 4000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(rng.normal(size=(n, len(ALL_FEATURES))), columns=ALL_FEATURES)
    df["trouble_share"] = rng.uniform(0, 1, n)
    logit = 4 * df["trouble_share"] - 2
    df["default_label"] = (rng.uniform(size=n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df


def test_probabilities_are_valid_and_informative():
    df = synthetic_frame()
    train, test = df.iloc[:3000], df.iloc[3000:]
    model = fit_xgb_default(train)
    proba = predict_xgb(model, test)
    assert proba.min() >= 0.0 and proba.max() <= 1.0
    assert roc_auc_score(test["default_label"], proba) > 0.7

def test_amount_ratio_recent_is_not_a_feature():
    assert "amount_ratio_recent" not in MODEL_FEATURES



def test_fit_is_reproducible():
    df = synthetic_frame()
    p1 = predict_xgb(fit_xgb_default(df.iloc[:400]), df.iloc[400:])
    p2 = predict_xgb(fit_xgb_default(df.iloc[:400]), df.iloc[400:])
    np.testing.assert_allclose(p1, p2)


def test_params_are_fixed_and_unweighted():
    assert "scale_pos_weight" not in XGB_PARAMS
    assert XGB_PARAMS["random_state"] == 42