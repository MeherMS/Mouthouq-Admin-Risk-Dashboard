import os

try:
    import streamlit as st
    _secret_url = st.secrets.get("API_URL")
except Exception:
    _secret_url = None

API_URL = _secret_url or os.environ.get("API_URL", "http://127.0.0.1:8000")
API_BASE_URL = API_URL
try:
    import streamlit as _st
    _secret_key = _st.secrets.get("API_KEY")
except Exception:
    _secret_key = None

API_KEY = _secret_key or os.environ.get("API_KEY", "")
# Seconds to wait for the API before showing an error.
REQUEST_TIMEOUT_SECONDS = 10

# Band colors (roadmap section 8). Keys match the band strings the API returns.
BAND_COLORS = {
    "low": "#2e7d32",     # green
    "medium": "#f9a825",  # amber
    "high": "#c62828",    # red
}

# Fraud bands are absolute scores (0-100), set in scripts/run_scoring.py.
FRAUD_MEDIUM_MIN = 40
FRAUD_HIGH_MIN = 70

# Default bands are percentile ranks across scored customers:
# High = top 1%, Medium = next 9%, Low = rest.
# Boundaries are approximate at 10,000 customers (a score of 90.01 is medium,
# 90.00 is low).
DEFAULT_MEDIUM_MIN = 90
DEFAULT_HIGH_MIN = 99

# Plain-language labels for model factors shown on profile pages.
# Keys are feature names from app/ml/features.py.
FACTOR_LABELS = {
    "events_90d": "Payment activity in last 90 days (includes installment plans)",
    "missed_share_90d": "Share of missed payments in last 90 days",
    "trouble_share_90d": "Share of late, partial, or missed payments in last 90 days",
    "late_share_90d": "Share of late payments in last 90 days",
    "trouble_trend": "Change in late or missed payments versus prior 90 days",
    "mean_amount_90d": "Average deal size in last 90 days",
    "amount_ratio_recent": "Recent deal size compared with earlier deals",
    "deals_30d": "Deals opened in last 30 days",
    "deals_90d": "Deals opened in last 90 days",
    "cancel_rate_90d": "Share of closed deals cancelled in last 90 days",
    "dispute_rate_90d": "Share of closed deals disputed in last 90 days",
    "account_age_days": "Account age in days",
}