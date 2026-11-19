from app.db import engine
from app.ml.data import load_tables
from app.ml.dataset import build_snapshot_dataset

tables = load_tables(engine)
df = build_snapshot_dataset(tables)
print(df.groupby("snapshot_date").size())
print(df.groupby("snapshot_date")[["default_label", "fraud_label"]].agg(["sum", "mean"]))