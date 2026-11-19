# %% [markdown]
# # Step 4b: Count-feature diagnostic (feature values only, no labels or predictions)
# Purpose: check whether the raw count features have long tails that the logistic model extrapolates into.
# The train distribution decides any transform. The test section only reports range, not performance.

# %% Setup
import sys
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from app.db import engine
from app.ml.data import load_tables
from app.ml.dataset import build_snapshot_dataset
from app.ml.default_model import MODEL_FEATURES, fit_default_model
from app.ml.split import split_by_time

COUNTS = ["n_payment_events", "n_deals", "deals_90d", "deals_30d", "deals_7d"]

# %% Build and split
tables = load_tables(engine)
dataset = build_snapshot_dataset(tables)
train, test = split_by_time(dataset)

# %% Train distribution of the count features
print("TRAIN distribution:")
print(train[COUNTS].describe(percentiles=[0.5, 0.9, 0.99, 0.999]).round(1).T.to_string())

# %% Skew: long tails show up as mean far above median
print("\nTRAIN mean / median:")
print((train[COUNTS].mean() / train[COUNTS].median().replace(0, np.nan)).round(2).to_string())

# %% Standardized extremes, using the scaler fit on train
model = fit_default_model(train)
scaler = model.named_steps["standardscaler"]
z_train = pd.DataFrame(scaler.transform(train[MODEL_FEATURES]), columns=MODEL_FEATURES)
z_test = pd.DataFrame(scaler.transform(test[MODEL_FEATURES]), columns=MODEL_FEATURES)

print("\nMax |z| on TRAIN:", z_train[COUNTS].abs().max().round(1).to_dict())
print("Max |z| on TEST: ", z_test[COUNTS].abs().max().round(1).to_dict())
print("\nTRAIN rows with |z| > 5 in n_payment_events:", int((z_train["n_payment_events"].abs() > 5).sum()))
print("TEST rows with |z| > 5 in n_payment_events:", int((z_test["n_payment_events"].abs() > 5).sum()))

# %% Payment events per deal, a candidate rate feature (distribution only)
per_deal_train = (train["n_payment_events"] / train["n_deals"].replace(0, np.nan)).dropna()
print("\nTRAIN events per deal:")
print(per_deal_train.describe(percentiles=[0.5, 0.9, 0.99]).round(2).to_string())

# %% Drift check on TRAINING cutoffs only (no test rows, no labels)
ratio = train["n_payment_events"] / train["n_deals"].replace(0, np.nan)
drift = pd.DataFrame({
    "n_payment_events_mean": train.groupby("snapshot_date")["n_payment_events"].mean(),
    "n_payment_events_p99": train.groupby("snapshot_date")["n_payment_events"].quantile(0.99),
    "n_deals_mean": train.groupby("snapshot_date")["n_deals"].mean(),
    "events_per_deal_mean": ratio.groupby(train["snapshot_date"]).mean(),
})
print("\nTRAIN drift by training cutoff:")
print(drift.round(3).to_string())


# %% Trailing-window drift check on TRAINING cutoffs only
from app.ml.split import TRAIN_CUTOFFS

def trailing_events(tables, cutoff, days=90):
    cutoff = pd.Timestamp(cutoff)
    tx = tables["transactions"][["id", "deal_id"]].rename(columns={"id": "transaction_id"})
    past = tables["deals"].loc[tables["deals"]["created_at"] < cutoff, ["id", "customer_id"]]
    past = past.rename(columns={"id": "deal_id"})
    pe = tables["payment_events"]
    pay = pe.merge(tx, on="transaction_id").merge(past, on="deal_id")
    win = pay[(pay["occurred_at"] < cutoff) & (pay["occurred_at"] >= cutoff - pd.Timedelta(days=days))]
    return win.groupby("customer_id").size()

rows = []
for c in TRAIN_CUTOFFS:
    in_snap = train["snapshot_date"] == c
    ids = train.loc[in_snap, "customer_id"]
    tr = trailing_events(tables, c).reindex(ids).fillna(0)
    rows.append({
        "cutoff": c.date(),
        "events_90d_mean": round(float(tr.mean()), 3),
        "events_90d_p99": float(tr.quantile(0.99)),
        "deals_90d_mean": round(float(train.loc[in_snap, "deals_90d"].mean()), 3),
        "cumulative_events_mean": round(float(train.loc[in_snap, "n_payment_events"].mean()), 3),
    })
print("\nTRAIN trailing-window drift by training cutoff:")
print(pd.DataFrame(rows).to_string(index=False))

# %% Feature-only warm-up check across ALL cutoffs (no labels, no predictions)
rows = []
for c in TRAIN_CUTOFFS:
    in_snap = dataset["snapshot_date"] == c
    ids = dataset.loc[in_snap, "customer_id"]
    tr = trailing_events(tables, c).reindex(ids).fillna(0)
    rows.append({
        "cutoff": c.date(),
        "events_90d_mean": round(float(tr.mean()), 3),
        "deals_90d_mean": round(float(dataset.loc[in_snap, "deals_90d"].mean()), 3),
    })
print("\nAll cutoffs, feature values only:")
print(pd.DataFrame(rows).to_string(index=False))