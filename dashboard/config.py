import os

# Base URL of the FastAPI backend. Override with an environment variable if needed.
#API_BASE_URL = os.getenv("ADMIN_API_URL", "http://127.0.0.1:8000").rstrip("/")


try:
    import streamlit as st
    _secret_url = st.secrets.get("API_URL")
except Exception:
    _secret_url = None

API_URL = _secret_url or os.environ.get("API_URL", "http://127.0.0.1:8000")


# Seconds to wait for the API before showing an error.
REQUEST_TIMEOUT_SECONDS = 10
API_BASE_URL = API_URL
# Band colors used across the dashboard (roadmap section 8).
# Keys are placeholders until we confirm the exact band strings the API returns.
BAND_COLORS = {
    "low": "#2e7d32",     # green
    "medium": "#f9a825",  # amber
    "high": "#c62828",    # red
}