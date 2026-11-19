# %% [markdown]
# # Step 2: Time-based split and rule-based fraud baseline
# Run top to bottom. The test cutoff (2026-08-01) is evaluated once, after the rule is fixed.

# %% Setup
import sys
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from app.config import *  # noqa: F401,F403  (kept minimal; remove if unused)
from app.db import engine
from app.ml.baselines import RULES, bootstrap_metrics, evaluate, rule_fraud_score
from app.ml.config import CUTOFFS
from app.ml.data import load_tables
from app.ml.dataset import build_snapshot_dataset
from app.ml.split import PURGED_CUTOFFS, TEST_CUTOFF, TRAIN_CUTOFFS, split_by_time

# %% Build dataset
tables = load_tables(engine)
dataset = build_snapshot_dataset(tables)
print(dataset.groupby("snapshot_date").size())

# %% Split
train, test = split_by_time(dataset)
print("train cutoffs:", [d.date() for d in TRAIN_CUTOFFS])
print("purged cutoffs:", [d.date() for d in PURGED_CUTOFFS])
print("test cutoff:  ", TEST_CUTOFF.date())
print("rows train/test:", len(train), len(test))
print("fraud positives train/test:", int(train["fraud_label"].sum()), int(test["fraud_label"].sum()))
print("default positives train/test:", int(train["default_label"].sum()), int(test["default_label"].sum()))

# %% Rule diagnostics on TRAIN only (used to understand the rules, not to tune them)
rows = []
for name, points, cond in RULES:
    fired = cond(train)
    rows.append({
        "rule": name,
        "points": points,
        "n_fired": int(fired.sum()),
        "fraud_rate_when_fired": train.loc[fired, "fraud_label"].mean() if fired.any() else np.nan,
    })
print(pd.DataFrame(rows).round(3).to_string(index=False))

# %% Test evaluation (run once)
test_score = rule_fraud_score(test)
res = evaluate(test["fraud_label"], test_score)
print("\nTest cutoff (2026-08-01):")
for k, v in res.items():
    print(f"  {k:16s} {v}")

ci = bootstrap_metrics(test["fraud_label"], test_score)
print("  ROC-AUC 95% CI:", tuple(round(x, 3) for x in ci["roc_auc_ci"]))
print("  PR-AUC  95% CI:", tuple(round(x, 3) for x in ci["pr_auc_ci"]))

# %% Stability across all cutoffs (descriptive only, not used for selection)
stab = []
for c in CUTOFFS:
    part = dataset[dataset["snapshot_date"] == c]
    r = evaluate(part["fraud_label"], rule_fraud_score(part))
    stab.append({"cutoff": c.date(), **r})
print(pd.DataFrame(stab).round(3).to_string(index=False))