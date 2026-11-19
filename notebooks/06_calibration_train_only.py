# %% [markdown]
# # Step 3d: Calibration diagnostic, TRAINING DATA ONLY
# This notebook never loads the test cutoff. It checks whether Platt scaling fit on
# in-sample training predictions changes anything. If it doesn't, we don't ship a calibration layer.

# %% Setup
import sys
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from app.db import engine
from app.ml.calibration import apply_platt, fit_platt
from app.ml.data import load_tables
from app.ml.dataset import build_snapshot_dataset
from app.ml.default_model import brier, fit_default_model, predict_default
from app.ml.split import split_by_time

# %% Build dataset and take the training side only
tables = load_tables(engine)
dataset = build_snapshot_dataset(tables)
train, _ = split_by_time(dataset)  # the test frame is discarded here and never used
y_train = train["default_label"].to_numpy()

# %% Fit the frozen model on training and get in-sample predictions
model = fit_default_model(train)
p_train = predict_default(model, train)

base_rate_train = y_train.mean()
print("training positives:", int(y_train.sum()), "of", len(y_train))
print("mean predicted (train):", round(float(p_train.mean()), 5))
print("observed rate (train): ", round(float(base_rate_train), 5))

# %% Platt fit on training predictions
platt = fit_platt(y_train, p_train)
print("\nPlatt slope:", round(float(platt.coef_[0][0]), 4),
      " intercept:", round(float(platt.intercept_[0]), 4))
print("(identity is slope 1, intercept 0)")

p_train_cal = apply_platt(platt, p_train)
print("\nBrier on TRAIN, before Platt:", round(brier(y_train, p_train), 6))
print("Brier on TRAIN, after Platt: ", round(brier(y_train, p_train_cal), 6))
print("max abs change in any prediction:", round(float(np.abs(p_train_cal - p_train).max()), 6))

# %% Calibration table on training data
bins = pd.qcut(p_train, 5, duplicates="drop")
tbl = pd.DataFrame({"pred": p_train, "obs": y_train, "bin": bins}).groupby("bin", observed=True).mean()
print(tbl.round(5).to_string())