"""Platt scaling: a logistic fit on the model's logits. Fit only on data you're allowed to use."""
import numpy as np
from sklearn.linear_model import LogisticRegression


def _logit(p) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p)).reshape(-1, 1)


def fit_platt(y, p) -> LogisticRegression:
    # C is large so the fit is effectively unregularized.
    lr = LogisticRegression(C=1e6, max_iter=1000)
    lr.fit(_logit(p), np.asarray(y).astype(int))
    return lr


def apply_platt(platt: LogisticRegression, p) -> np.ndarray:
    return platt.predict_proba(_logit(p))[:, 1]