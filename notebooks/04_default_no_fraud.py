# %% [markdown]
# # Step 3b: Default baseline without fraud actors (labeled secondary result)
# Fraud actors are removed from every snapshot. Their default label is 0 by construction,
# so removing them only removes negatives. The frozen full-population results are printed
# below for comparison. The test cutoff (2026-08-01) has now been used for a third evaluation.

# %% Setup
import sys
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from app.db import engine
from app.ml.baselines import bootstrap_metrics, evaluate
from app.ml.config import CUTOFFS
from app.ml.data import load_tables
from app.ml.dataset import build_snapshot_dataset
from app.ml.default_model import (
    MODEL_FEATURES,
    NON_PAYMENT_FEATURES,
    brier,
    calibration_table,
    fit_default_model,
    predict_default,
)
from app.ml.population import drop_customers, fraud_actor_customer_ids
from app.ml.split import PURGED_CUTOFFS, TEST_CUTOFF, TRAIN_CUTOFFS, split_by_time

# Frozen full-population results from Step 3 (for side-by-side reference only).
FROZEN_FULL = {"roc_auc": 0.934, "pr_auc": 0.171, "precision_at_k": 0.230, "brier": 0.01204}

# %% Build dataset and remove fraud actors
tables = load_tables(engine)
full = build_snapshot_dataset(tables)
fraud_ids = fraud_actor_customer_ids(engine)
dataset = drop_customers(full, fraud_ids)

print("fraud actors removed:", len(fraud_ids))
print("rows full -> no-fraud:", len(full), "->", len(dataset))
print("default positives full -> no-fraud:",
      int(full["default_label"].sum()), "->", int(dataset["default_label"].sum()))
assert full["default_label"].sum() == dataset["default_label"].sum(), \
    "fraud actors should have no default positives"

# %% Split
train, test = split_by_time(dataset)
print("train cutoffs:", [d.date() for d in TRAIN_CUTOFFS])
print("purged cutoffs:", [d.date() for d in PURGED_CUTOFFS])
print("test cutoff:  ", TEST_CUTOFF.date())
print("rows train/test:", len(train), len(test))
print("default positives train/test:", int(train["default_label"].sum()), int(test["default_label"].sum()))
print("test base rate:", round(float(test["default_label"].mean()), 5))

# %% Fit on train only and inspect coefficients
model = fit_default_model(train)
coefs = pd.Series(model[-1].coef_[0], index=MODEL_FEATURES)
print(coefs.reindex(coefs.abs().sort_values(ascending=False).index).round(3).to_string())

# %% Test evaluation (run once for this population)
y_test = test["default_label"]
p_test = predict_default(model, test)
res = evaluate(y_test, p_test)
ci = bootstrap_metrics(y_test, p_test)

print("\nTest cutoff (2026-08-01), no-fraud population:")
for k, v in res.items():
    print(f"  {k:16s} {v}")
print("  ROC-AUC 95% CI:", tuple(round(float(x), 3) for x in ci["roc_auc_ci"]))
print("  PR-AUC  95% CI:", tuple(round(float(x), 3) for x in ci["pr_auc_ci"]))
print("  frozen full-population ROC-AUC:", FROZEN_FULL["roc_auc"],
      "PR-AUC:", FROZEN_FULL["pr_auc"], "precision_at_k:", FROZEN_FULL["precision_at_k"])

# %% Calibration on test
base_rate_train = train["default_label"].mean()
base_rate_test = y_test.mean()
print("Brier, model:                       ", round(brier(y_test, p_test), 5))
print("Brier, constant at train rate:      ", round(brier(y_test, np.full(len(y_test), base_rate_train)), 5))
print("Brier, constant at test rate (ref): ", round(brier(y_test, np.full(len(y_test), base_rate_test)), 5))
print("Mean predicted vs observed on test: ", round(float(p_test.mean()), 5), round(float(base_rate_test), 5))
print(calibration_table(y_test, p_test).round(4).to_string(index=False))

# %% Ablation: remove payment history
ablation = fit_default_model(train, NON_PAYMENT_FEATURES)
p_abl = predict_default(ablation, test, NON_PAYMENT_FEATURES)
res_abl = evaluate(y_test, p_abl)
ci_abl = bootstrap_metrics(y_test, p_abl)

print("\nTest cutoff, no-fraud population, WITHOUT payment features:")
for k, v in res_abl.items():
    print(f"  {k:16s} {v}")
print("  ROC-AUC 95% CI:", tuple(round(float(x), 3) for x in ci_abl["roc_auc_ci"]))
print("  PR-AUC  95% CI:", tuple(round(float(x), 3) for x in ci_abl["pr_auc_ci"]))

# %% Stability across all cutoffs (descriptive; model not refit)
stab = []
for c in CUTOFFS:
    part = dataset[dataset["snapshot_date"] == c]
    r = evaluate(part["default_label"], predict_default(model, part))
    stab.append({"cutoff": c.date(), **r})
print(pd.DataFrame(stab).round(3).to_string(index=False))