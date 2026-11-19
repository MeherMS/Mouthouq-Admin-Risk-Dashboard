# %% [markdown]
# # Step 3c: Default-risk gradient boosting (XGBoost), one-shot test evaluation
# Trained on the four training cutoffs only. The test cutoff (2026-08-01) is evaluated once.
# Comparison is against the frozen logistic regression, using the same test rows.

# %% Setup
import sys
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from app.db import engine
from app.ml.baselines import bootstrap_metrics, evaluate
from app.ml.config import CUTOFFS
from app.ml.data import load_tables
from app.ml.dataset import build_snapshot_dataset
from app.ml.default_model import (
    MODEL_FEATURES,
    brier,
    calibration_table,
    fit_default_model,
    predict_default,
)
from app.ml.split import PURGED_CUTOFFS, TEST_CUTOFF, TRAIN_CUTOFFS, split_by_time
from app.ml.xgb_model import XGB_PARAMS, fit_xgb_default, predict_xgb

# Frozen logistic regression results from Step 3 (full population). Reference only.
FROZEN_LR = {"roc_auc": 0.934, "pr_auc": 0.171, "precision_at_k": 0.230, "brier": 0.01214}

# %% Build dataset and split (full population, primary)
tables = load_tables(engine)
dataset = build_snapshot_dataset(tables)
train, test = split_by_time(dataset)

print("train cutoffs:", [d.date() for d in TRAIN_CUTOFFS])
print("purged cutoffs:", [d.date() for d in PURGED_CUTOFFS])
print("test cutoff:  ", TEST_CUTOFF.date())
print("rows train/test:", len(train), len(test))
print("default positives train/test:", int(train["default_label"].sum()), int(test["default_label"].sum()))
print("XGB params (fixed before evaluation):", XGB_PARAMS)

# %% Fit on train only
xgb = fit_xgb_default(train)
importance = pd.Series(xgb.feature_importances_, index=MODEL_FEATURES)
print("\nGain importance (train-fitted model):")
print(importance.sort_values(ascending=False).round(4).to_string())

# %% Test evaluation (run once)
y_test = test["default_label"]
p_xgb = predict_xgb(xgb, test)
res = evaluate(y_test, p_xgb)
ci = bootstrap_metrics(y_test, p_xgb)

print("\nTest cutoff (2026-08-01), XGBoost, full population:")
for k, v in res.items():
    print(f"  {k:16s} {v}")
print("  ROC-AUC 95% CI:", tuple(round(float(x), 3) for x in ci["roc_auc_ci"]))
print("  PR-AUC  95% CI:", tuple(round(float(x), 3) for x in ci["pr_auc_ci"]))

# %% Head-to-head with the frozen logistic regression on the same test rows
lr = fit_default_model(train)  # refit with identical inputs, deterministic
p_lr = predict_default(lr, test)
res_lr = evaluate(y_test, p_lr)
print("\nFrozen logistic regression, same test rows (recomputed):")
print("  roc_auc", round(res_lr["roc_auc"], 3), "pr_auc", round(res_lr["pr_auc"], 3),
      "precision_at_k", round(res_lr["precision_at_k"], 3))
print("  frozen record:", FROZEN_LR)


def paired_bootstrap_auc_diff(y, p_a, p_b, n_boot: int = 1000, seed: int = 42):
    """ROC-AUC(b) minus ROC-AUC(a) on the same resampled rows. Returns 95% CI and P(b > a)."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y).astype(int)
    p_a = np.asarray(p_a, dtype=float)
    p_b = np.asarray(p_b, dtype=float)
    n = len(y)
    diffs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        yb = y[idx]
        if yb.min() == yb.max():
            continue
        diffs.append(roc_auc_score(yb, p_b[idx]) - roc_auc_score(yb, p_a[idx]))
    d = np.array(diffs)
    return tuple(np.percentile(d, [2.5, 97.5])), float((d > 0).mean())

ci_diff, p_better = paired_bootstrap_auc_diff(y_test, p_lr, p_xgb)
print("\nROC-AUC difference, XGBoost minus logistic (paired bootstrap):")
print("  95% CI:", tuple(round(float(x), 3) for x in ci_diff), " P(XGBoost better):", round(p_better, 3))

# %% Calibration and Brier against constant baselines
base_rate_train = train["default_label"].mean()
base_rate_test = y_test.mean()
print("\nBrier, XGBoost:                      ", round(brier(y_test, p_xgb), 5))
print("Brier, logistic (recomputed):        ", round(brier(y_test, p_lr), 5))
print("Brier, constant at train rate:       ", round(brier(y_test, np.full(len(y_test), base_rate_train)), 5))
print("Brier, constant at test rate (ref):  ", round(brier(y_test, np.full(len(y_test), base_rate_test)), 5))
print("Mean predicted vs observed, XGBoost: ", round(float(p_xgb.mean()), 5), round(float(base_rate_test), 5))
print(calibration_table(y_test, p_xgb).round(4).to_string(index=False))

# %% Stability across cutoffs (descriptive; model not refit)
stab = []
for c in CUTOFFS:
    part = dataset[dataset["snapshot_date"] == c]
    r = evaluate(part["default_label"], predict_xgb(xgb, part))
    stab.append({"cutoff": c.date(), **r})
print(pd.DataFrame(stab).round(3).to_string(index=False))