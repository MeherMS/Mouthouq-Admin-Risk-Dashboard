"""Default-risk baseline: standardized logistic regression, fit on training cutoffs only."""
import numpy as np
import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.features import ALL_FEATURES

# amount_ratio_recent is dropped: median 1.0 for every profile, no separation (Phase 1 finding).
MODEL_FEATURES = [f for f in ALL_FEATURES if f != "amount_ratio_recent"]

# Payment-derived features, used for the ablation that removes payment history.
PAYMENT_FEATURES = [
    "n_payment_events", "trouble_share", "missed_share", "late_share", "trouble_trend",
]
NON_PAYMENT_FEATURES = [f for f in MODEL_FEATURES if f not in PAYMENT_FEATURES]


def make_default_model(random_state: int = 42):
    # No class weighting: weighting would shift predicted probabilities and break calibration.
    return make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, random_state=random_state),
    )


def fit_default_model(train: pd.DataFrame, features=MODEL_FEATURES):
    model = make_default_model()
    model.fit(train[features], train["default_label"])
    return model


def predict_default(model, df: pd.DataFrame, features=MODEL_FEATURES) -> np.ndarray:
    return model.predict_proba(df[features])[:, 1]


def brier(y_true, proba) -> float:
    return float(brier_score_loss(np.asarray(y_true).astype(int), np.asarray(proba, dtype=float)))


def calibration_table(y_true, proba, n_bins: int = 5) -> pd.DataFrame:
    observed, predicted = calibration_curve(
        np.asarray(y_true).astype(int), np.asarray(proba, dtype=float),
        n_bins=n_bins, strategy="quantile",
    )
    return pd.DataFrame({"mean_predicted": predicted, "observed_rate": observed})