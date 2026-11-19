from app.db import engine
from app.ml.data import load_tables
import pandas as pd

t = load_tables(engine)
deals = t["deals"]
cust = t["customers"][["id", "created_at"]].rename(
    columns={"id": "customer_id", "created_at": "signup_at"}
)

fraud = deals[deals["is_fraud"].astype(bool)].merge(cust, on="customer_id")
fraud["days_after_signup"] = (fraud["created_at"] - fraud["signup_at"]).dt.days

print("fraud deals:", len(fraud), "| fraud customers:", fraud["customer_id"].nunique())
print("\nfraud deals by month:")
print(fraud.groupby(fraud["created_at"].dt.to_period("M")).size())
print("\ndays from signup to fraud deal:")
print(fraud["days_after_signup"].describe())
print("\nsignup dates of fraud customers:")
print(fraud.groupby("customer_id")["signup_at"].first().dt.to_period("M").value_counts().sort_index())