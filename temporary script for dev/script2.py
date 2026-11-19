from app.db import engine
from app.ml.data import load_tables
import pandas as pd

t = load_tables(engine)
d = t["deals"].copy()
window_start = pd.Timestamp("2025-11-15")
d["before_window"] = d["created_at"] < window_start
d["before_signup"] = d.merge(
    t["customers"][["id", "created_at"]].rename(columns={"id": "customer_id", "created_at": "signup_at"}),
    on="customer_id", how="left"
)["created_at"].values < d.merge(
    t["customers"][["id", "created_at"]].rename(columns={"id": "customer_id", "created_at": "signup_at"}),
    on="customer_id", how="left"
)["signup_at"].values

print(d.groupby("is_fraud")[["before_window", "before_signup"]].agg(["sum", "mean"]))
print("earliest deal:", d["created_at"].min())