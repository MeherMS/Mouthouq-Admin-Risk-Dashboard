"""Exact per-customer explanations for the logistic default model.

For a standardized linear model, feature j's contribution is coef_j * z_j, where
z_j = (x_j - training mean) / training std. The intercept is the log-odds of the
average training customer, so: logit = intercept + sum(contributions).
These values are exact, so no approximation like SHAP's sampling is involved.
"""
import numpy as np
import pandas as pd

from app.ml.default_model import MODEL_FEATURES


def contributions(model, df: pd.DataFrame, features=MODEL_FEATURES) -> pd.DataFrame:
    scaler = model.named_steps["standardscaler"]
    lr = model.named_steps["logisticregression"]
    z = scaler.transform(df[features])
    return pd.DataFrame(z * lr.coef_[0], index=df.index, columns=features)


def check_additivity(model, df: pd.DataFrame, features=MODEL_FEATURES) -> float:
    """Largest gap between intercept + sum(contributions) and the model's own logit."""
    lr = model.named_steps["logisticregression"]
    c = contributions(model, df, features)
    recon = lr.intercept_[0] + c.sum(axis=1).to_numpy()
    actual = model.decision_function(df[features])
    return float(np.max(np.abs(recon - actual)))


def global_importance(model, df: pd.DataFrame, features=MODEL_FEATURES) -> pd.Series:
    """Mean absolute contribution per feature, in log-odds units."""
    return contributions(model, df, features).abs().mean().sort_values(ascending=False)


def top_factors(model, df: pd.DataFrame, features=MODEL_FEATURES, k: int = 3) -> pd.Series:
    """Top k features by absolute contribution, one list per row. Stored as JSON in risk_scores."""
    c = contributions(model, df, features)
    out = {}
    for idx, row in c.iterrows():
        top = row.reindex(row.abs().sort_values(ascending=False).index[:k])
        out[idx] = [
            {
                "feature": f,
                "contribution": float(v),
                "direction": "raises risk" if v > 0 else "lowers risk",
            }
            for f, v in top.items()
        ]
    return pd.Series(out, name="top_factors")