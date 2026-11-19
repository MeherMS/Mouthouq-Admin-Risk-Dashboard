"""Default-risk gradient boosting (XGBoost). Hyperparameters are fixed before any test evaluation.

Do not tune XGB_PARAMS on the test cutoff. Changing them after seeing test results
invalidates the one-shot evaluation.
"""
import numpy as np
import pandas as pd
from xgboost import XGBClassifier

from app.ml.default_model import MODEL_FEATURES

XGB_PARAMS = dict(
    n_estimators=200,
    max_depth=3,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=5,
    reg_lambda=1.0,
    random_state=42,
    n_jobs=1,  # single thread, so results are reproducible across machines
    eval_metric="logloss",
)


def make_xgb_default_model():
    # No scale_pos_weight: weighting would shift probabilities, same reason as the logistic model.
    return XGBClassifier(**XGB_PARAMS)


def fit_xgb_default(train: pd.DataFrame, features=MODEL_FEATURES):
    model = make_xgb_default_model()
    model.fit(train[features], train["default_label"])
    return model


def predict_xgb(model, df: pd.DataFrame, features=MODEL_FEATURES) -> np.ndarray:
    return model.predict_proba(df[features])[:, 1]