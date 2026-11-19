"""Rule-based fraud score (0 to 100) and evaluation helpers.

The rules and points are fixed here. Do not tune them on the test cutoff.
They follow the fraud signals in roadmap section 1: velocity, identity
mismatch (shared phone), cancellations, and disputes.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

RULES = [
    # (name, points, condition on a customer-feature frame)
    ("shared_phone", 25, lambda d: d["shared_phone_count"] >= 1),
    ("new_account", 20, lambda d: d["account_age_days"] < 120),
    ("velocity_30d", 20, lambda d: d["deals_30d"] >= 3),
    ("cancellations", 20, lambda d: (d["n_deals"] >= 2) & (d["cancel_rate"] >= 0.25)),
    ("disputes", 15, lambda d: d["dispute_rate"] >= 0.2),
]


def rule_fraud_score(df: pd.DataFrame) -> pd.Series:
    score = pd.Series(0.0, index=df.index)
    for _, points, cond in RULES:
        score += np.where(cond(df), points, 0)
    return score.rename("fraud_rule_score")


def evaluate(y_true, score, review_frac: float = 0.01) -> dict:
    """ROC-AUC, PR-AUC, and precision/recall for a review queue of the top review_frac."""
    y = np.asarray(y_true).astype(int)
    s = np.asarray(score, dtype=float)
    n = len(y)
    k = max(1, int(round(n * review_frac)))

    order = np.argsort(-s, kind="stable")
    top = y[order[:k]]
    cut_score = s[order[k - 1]]
    total_pos = y.sum()

    return {
        "n": n,
        "positives": int(total_pos),
        "base_rate": float(y.mean()),
        "roc_auc": float(roc_auc_score(y, s)) if 0 < total_pos < n else np.nan,
        "pr_auc": float(average_precision_score(y, s)) if total_pos > 0 else np.nan,
        "review_k": k,
        "precision_at_k": float(top.mean()),
        "recall_at_k": float(top.sum() / total_pos) if total_pos > 0 else np.nan,
        "tied_at_cut": int((s == cut_score).sum()),
    }


def bootstrap_metrics(y_true, score, n_boot: int = 1000, seed: int = 42) -> dict:
    """95% bootstrap intervals for ROC-AUC and PR-AUC."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y_true).astype(int)
    s = np.asarray(score, dtype=float)
    n = len(y)
    roc, pr = [], []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        yb = y[idx]
        if yb.min() == yb.max():
            continue  # need both classes in the resample
        roc.append(roc_auc_score(yb, s[idx]))
        pr.append(average_precision_score(yb, s[idx]))
    return {
        "roc_auc_ci": tuple(np.percentile(roc, [2.5, 97.5])),
        "pr_auc_ci": tuple(np.percentile(pr, [2.5, 97.5])),
    }