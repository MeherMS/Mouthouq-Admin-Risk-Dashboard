# %% [markdown]
# # Step 4: Explanations for the default model
# Uses the frozen logistic regression, fit on training cutoffs only. Explanations are
# exact contributions in log-odds. synthetic_profile is shown for validation only and is
# never a model input.

# %% Setup
import sys
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

import pandas as pd

from app.db import engine
from app.ml.data import load_tables
from app.ml.dataset import build_snapshot_dataset
from app.ml.default_model import fit_default_model, predict_default
from app.ml.explain import check_additivity, global_importance, top_factors
from app.ml.split import split_by_time

# %% Build dataset, split, fit on training only
tables = load_tables(engine)
dataset = build_snapshot_dataset(tables)
train, test = split_by_time(dataset)
model = fit_default_model(train)

# %% Sanity: explanations add up to the model's logit
print("max additivity gap on test (log-odds):", check_additivity(model, test))

# %% Global importance on test
print("\nMean absolute contribution (log-odds), test cutoff:")
print(global_importance(model, test).round(3).to_string())

# %% Top-scoring test customers with their top 3 factors
test = test.assign(p_default=predict_default(model, test))
top = test.sort_values("p_default", ascending=False).head(10)
tf = top_factors(model, top, k=3)
# Read separately: the profile is validation-only and must not enter the feature pipeline.
profiles = pd.read_sql("SELECT id, synthetic_profile FROM customers", engine).set_index("id")["synthetic_profile"]

print("\nTop 10 test customers by predicted default risk:")
for idx, row in top.iterrows():
    cid = int(row["customer_id"])
    print(f"\ncustomer {cid}  p_default={row['p_default']:.3f}  "
          f"(validation only: profile={profiles[cid]})")
    for f in tf[idx]:
        print(f"   {f['feature']:20s} {f['contribution']:+.3f}  {f['direction']}")