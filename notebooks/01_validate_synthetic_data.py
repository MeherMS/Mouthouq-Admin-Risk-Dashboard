# %% [markdown]
# # Step 5: Validate synthetic data (Phase 1 exit check)
# Run the cells in order. Each cell depends on the ones before it.

# %% Setup
import sys
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from app.db import SessionLocal, engine
from app.synthetic.config import FULL
from app.synthetic.history import load_db_ids, rebuild_population

SIM_END = pd.Timestamp(FULL.simulation_end).tz_convert(None)
RECENT_CUTOFF = SIM_END - pd.Timedelta(days=90)
PROFILE_ORDER = ["healthy", "default_prone", "fraud_actor"]

# %% Load tables
def read(table: str) -> pd.DataFrame:
    return pd.read_sql(f"SELECT * FROM {table}", engine)


def to_naive_utc(series: pd.Series) -> pd.Series:
    """Stored timestamps may or may not carry a timezone. Normalize to naive UTC."""
    return pd.to_datetime(series, utc=True).dt.tz_convert(None)


customers = read("customers")
stores = read("stores")
deals = read("deals")
transactions = read("transactions")
events = read("payment_events")

customers["created_at"] = to_naive_utc(customers["created_at"])
stores["created_at"] = to_naive_utc(stores["created_at"])
deals["created_at"] = to_naive_utc(deals["created_at"])
deals["closed_at"] = to_naive_utc(deals["closed_at"])
transactions["timestamp"] = to_naive_utc(transactions["timestamp"])
events["occurred_at"] = to_naive_utc(events["occurred_at"])
deals["amount_sar"] = deals["amount_sar"].astype(float)

print({
    "customers": len(customers),
    "stores": len(stores),
    "deals": len(deals),
    "transactions": len(transactions),
    "payment_events": len(events),
})

# %% Data integrity checks
required = {
    "customers": (customers, ["name", "national_id_hash", "phone", "email", "created_at", "synthetic_profile"]),
    "deals": (deals, ["customer_id", "store_id", "amount_sar", "status", "created_at", "is_fraud"]),
    "transactions": (transactions, ["deal_id", "amount_sar", "method", "status", "timestamp"]),
    "payment_events": (events, ["transaction_id", "event_type", "occurred_at"]),
}
for name, (frame, cols) in required.items():
    nulls = frame[cols].isna().sum()
    assert nulls.sum() == 0, f"Nulls in {name}:\n{nulls[nulls > 0]}"
print("PASS  no nulls in required fields")

assert deals["customer_id"].isin(customers["id"]).all()
assert deals["store_id"].isin(stores["id"]).all()
print("PASS  foreign keys valid")

assert (deals["created_at"] <= SIM_END).all()
assert (events["occurred_at"] <= SIM_END).all()
print("PASS  no deals or events after simulation end")

# %% Customer features
# Features are built from behavior, never from default_label.
PAYMENT_TYPES = ["on_time", "late", "partial", "missed"]

txn_to_deal = transactions[["id", "deal_id"]].rename(columns={"id": "transaction_id"})
deal_to_cust = deals[["id", "customer_id"]].rename(columns={"id": "deal_id"})
ev = (
    events[["transaction_id", "event_type", "occurred_at"]]
    .merge(txn_to_deal, on="transaction_id")
    .merge(deal_to_cust, on="deal_id")
)

# Ordinary payments only. Refunds and chargebacks are not payment behavior.
pay = ev[ev["event_type"].isin(PAYMENT_TYPES)].copy()
pay["is_trouble"] = pay["event_type"].isin(["late", "partial", "missed"]).astype(int)
pay["is_missed"] = (pay["event_type"] == "missed").astype(int)
pay["is_late"] = (pay["event_type"] == "late").astype(int)
pay["is_recent"] = pay["occurred_at"] > RECENT_CUTOFF

pay_feat = pay.groupby("customer_id").agg(
    trouble_share=("is_trouble", "mean"),
    missed_share=("is_missed", "mean"),
    late_share=("is_late", "mean"),
)
trouble_recent = pay[pay["is_recent"]].groupby("customer_id")["is_trouble"].mean().rename("trouble_recent")
trouble_earlier = pay[~pay["is_recent"]].groupby("customer_id")["is_trouble"].mean().rename("trouble_earlier")

deals["is_cancelled"] = (deals["status"] == "cancelled").astype(int)
deals["is_disputed"] = (deals["status"] == "disputed").astype(int)
deal_feat = deals.groupby("customer_id").agg(
    n_deals=("id", "size"),
    cancel_rate=("is_cancelled", "mean"),
    dispute_rate=("is_disputed", "mean"),
    mean_amount=("amount_sar", "mean"),
    max_amount=("amount_sar", "max"),
)
for days in (7, 30, 90):
    cutoff = SIM_END - pd.Timedelta(days=days)
    deal_feat[f"deals_{days}d"] = deals[deals["created_at"] > cutoff].groupby("customer_id").size()

recent_amount = deals[deals["created_at"] > RECENT_CUTOFF].groupby("customer_id")["amount_sar"].mean()
deal_feat["amount_ratio_recent"] = recent_amount / deal_feat["mean_amount"]

feat = (
    customers[["id", "synthetic_profile", "created_at", "phone", "default_label"]]
    .rename(columns={"id": "customer_id"})
    .set_index("customer_id")
)
feat["account_age_days"] = (SIM_END - feat["created_at"]).dt.days
feat["shared_phone_count"] = feat.groupby("phone")["phone"].transform("size") - 1
feat = feat.join(deal_feat).join(pay_feat).join(trouble_recent).join(trouble_earlier)

fill_zero = ["n_deals", "cancel_rate", "dispute_rate", "mean_amount", "max_amount",
             "deals_7d", "deals_30d", "deals_90d", "trouble_share", "missed_share", "late_share"]
feat[fill_zero] = feat[fill_zero].fillna(0)
feat["amount_ratio_recent"] = feat["amount_ratio_recent"].fillna(1.0)
feat["trouble_trend"] = (feat["trouble_recent"] - feat["trouble_earlier"]).fillna(0)

FEATURES = [
    "account_age_days", "shared_phone_count", "n_deals", "deals_7d", "deals_30d", "deals_90d",
    "cancel_rate", "dispute_rate", "mean_amount", "max_amount", "amount_ratio_recent",
    "trouble_share", "missed_share", "late_share", "trouble_trend",
]
print(f"Built {len(feat)} customer feature rows, {len(FEATURES)} features.")

# %% Profile comparison (medians)
print(feat.groupby("synthetic_profile")[FEATURES].median().T.round(3))

# %% Charts: key features by profile
key = ["account_age_days", "deals_30d", "cancel_rate", "dispute_rate",
       "trouble_share", "trouble_trend", "amount_ratio_recent", "shared_phone_count"]

fig, axes = plt.subplots(2, 4, figsize=(18, 8))
for ax, col in zip(axes.ravel(), key):
    data = [feat.loc[feat["synthetic_profile"] == p, col] for p in PROFILE_ORDER]
    ax.boxplot(data, showfliers=False)
    ax.set_xticks(range(1, len(PROFILE_ORDER) + 1), PROFILE_ORDER, rotation=20)
    ax.set_title(col)
plt.suptitle("Customer features by synthetic profile", y=1.00)
plt.tight_layout()
plt.show()

# %% Separability: single-feature AUC for each pair of profiles
def pair_auc(df: pd.DataFrame, pos: str, neg: str) -> pd.Series:
    sub = df[df["synthetic_profile"].isin([pos, neg])]
    y = (sub["synthetic_profile"] == pos).astype(int)
    out = {}
    for col in FEATURES:
        out[col] = roc_auc_score(y, sub[col]) if sub[col].nunique() > 1 else np.nan
    return pd.Series(out)


auc_table = pd.DataFrame({
    "default_prone vs healthy": pair_auc(feat, "default_prone", "healthy"),
    "fraud_actor vs healthy": pair_auc(feat, "fraud_actor", "healthy"),
    "fraud_actor vs default_prone": pair_auc(feat, "fraud_actor", "default_prone"),
})
print("Single-feature AUC (0.5 = no separation, 1.0 = perfect):")
print(auc_table.round(3))

# %% Labels vs profiles
print("\nDefault label by profile:")
print(pd.crosstab(feat["synthetic_profile"], feat["default_label"], margins=True))

# %% Store check
with SessionLocal() as session:
    _, pop_stores = load_db_ids(session, *rebuild_population(FULL))

store_profile = pop_stores.set_index("db_id")["profile"]
sd = deals.groupby("store_id").agg(
    n_deals=("id", "size"),
    dispute_rate=("is_disputed", "mean"),
    mean_amount=("amount_sar", "mean"),
)
sd["profile"] = store_profile.reindex(sd.index)
sd["category"] = stores.set_index("id")["category"].reindex(sd.index)
sd["price_index"] = sd["mean_amount"] / sd.groupby("category")["mean_amount"].transform("median")

print("Store medians by profile:")
print(sd.groupby("profile")[["dispute_rate", "price_index"]].median().round(3))

# %% Phase 1 exit checks (first-pass thresholds, adjust if needed)
rates = feat.groupby("synthetic_profile")["default_label"].mean()
fraud_deals = int(deals["is_fraud"].sum())
best = ((auc_table - 0.5).abs() + 0.5).max()
fraud_months = deals.loc[deals["is_fraud"].astype(bool), "created_at"].dt.to_period("M").nunique()
checks = [
    ("Default-prone label rate in 30-45%",
     0.30 <= rates["default_prone"] <= 0.45, f"{rates['default_prone']:.1%}"),
    ("Healthy label rate under 2%",
     rates["healthy"] < 0.02, f"{rates['healthy']:.1%}"),
    ("Fraud deals at least 50",
     fraud_deals >= 50, str(fraud_deals)),
    ("Default-prone vs healthy separable (best AUC >= 0.75)",
     best["default_prone vs healthy"] >= 0.75, f"{best['default_prone vs healthy']:.3f}"),
    ("Fraud vs healthy separable (best AUC >= 0.75)",
     best["fraud_actor vs healthy"] >= 0.75, f"{best['fraud_actor vs healthy']:.3f}"),
    ("Fraud vs default-prone separable (best AUC >= 0.75)",
     best["fraud_actor vs default_prone"] >= 0.75, f"{best['fraud_actor vs default_prone']:.3f}"),
    ("High-dispute stores above legitimate stores",
     sd.groupby("profile")["dispute_rate"].median()["high_dispute"]
     > sd.groupby("profile")["dispute_rate"].median()["legitimate"],
     "see store table above"),
     ("Fraud deals span at least 6 calendar months",
     fraud_months >= 6, str(fraud_months)),
]

print()
for name, ok, value in checks:
    print(f"{'PASS' if ok else 'FAIL'}  {name}  [{value}]")

    # %% Artifact check: near-perfect single features
suspects = []
for pair in auc_table.columns:
    for feat_name, auc in auc_table[pair].dropna().items():
        if max(auc, 1 - auc) >= 0.98:
            suspects.append((pair, feat_name, round(float(auc), 3)))

if suspects:
    print("WARN  near-perfect single features (check whether each is a designed signal or an artifact):")
    for s in suspects:
        print("     ", s)
else:
    print("PASS  no near-perfect single features")

# Deals must fall inside the history window and after their customer's signup.
WINDOW_START = SIM_END - pd.Timedelta(days=FULL.history_days)
deals_chk = deals.merge(
    customers[["id", "created_at"]].rename(columns={"id": "customer_id", "created_at": "signup_at"}),
    on="customer_id",
)
n_before_window = int((deals_chk["created_at"] < WINDOW_START).sum())
n_before_signup = int((deals_chk["created_at"] < deals_chk["signup_at"]).sum())

assert n_before_window == 0, f"{n_before_window} deals before history window"
print("PASS  no deals before history window")

assert n_before_signup == 0, f"{n_before_signup} deals before customer signup"
print("PASS  no deals before customer signup")