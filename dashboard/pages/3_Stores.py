import pandas as pd
import streamlit as st

import api_client
from api_client import ApiError
from common import (
    BAND_OPTIONS,
    band_badge,
    fmt_date,
    fmt_money,
    fmt_score,
    render_actions,
    render_history,
    render_note_form,
    render_score_history,
    render_sidebar,
    render_transaction_timeline,
    show_feedback,
    style_bands,
)

st.set_page_config(page_title="Stores", layout="wide")
render_sidebar()
st.title("Stores")
st.caption("Store risk scores are not built yet. All stores show as Unscored until the store model is added.")

# Matches AccountStatus in app/models.py.
ACCOUNT_STATUS_OPTIONS = ["Any", "active", "pending", "frozen", "rejected"]
# Matches the Store.category and Store.city values in the database.
CATEGORY_OPTIONS = ["Any", "automotive", "education", "electronics", "fashion", "furniture", "healthcare", "travel"]
CITY_OPTIONS = ["Any", "Dammam", "Jeddah", "Khobar", "Madinah", "Makkah", "Riyadh"]
SORT_OPTIONS = {
    "Store ID": "id",
    "Name": "name",
    "Created": "created_at",
    "Fraud score": "fraud_score",
    "Default score": "default_score",
}
PAGE_SIZE = 50

# Stores support approve and reject, not freeze.
STORE_ACTIONS = [
    ("Approve store", "approve", "Store approved."),
    ("Reject store", "reject", "Store rejected."),
    ("Flag for review", "flag-review", "Flagged for review."),
]


def flatten_store(s: dict) -> dict:
    sc = s.get("scores") or {}
    return {
        "ID": s["id"],
        "Name": s["name"],
        "Category": s["category"],
        "City": s["city"],
        "Registration no.": s["commercial_registration_no"],
        "Status": s["account_status"],
        "Fraud score": sc.get("fraud_score"),
        "Fraud band": sc.get("fraud_band"),
        "Default score": sc.get("default_score"),
        "Default band": sc.get("default_band"),
        "Model": sc.get("model_version") or "—",
        "Created": fmt_date(s["created_at"]),
    }

def fmt_rate(value: float | None) -> str:
    # Assumes dispute_rate is a fraction (0.15 = 15%). See questions.
    return "—" if value is None else f"{value * 100:.1f}%"


# ---------- Filters ----------

c1, c2, c3, c4 = st.columns([3, 1.5, 1.5, 1.5])
q = c1.text_input("Search name or registration number")
status = c2.selectbox("Account status", ACCOUNT_STATUS_OPTIONS)
fraud_band = c3.selectbox("Fraud band", BAND_OPTIONS)
default_band = c4.selectbox("Default band", BAND_OPTIONS)

c5, c6, c7, c8 = st.columns([2, 2, 2, 1])
category = c5.selectbox("Category", CATEGORY_OPTIONS)
city = c6.selectbox("City", CITY_OPTIONS)
sort_label = c7.selectbox("Sort by", list(SORT_OPTIONS), index=0)
order = c8.selectbox("Order", ["asc", "desc"], index=0)

# Reset to the first page whenever a filter or sort changes.
filters = (q, status, fraud_band, default_band, category, city, sort_label, order)
if st.session_state.get("store_filters") != filters:
    st.session_state["store_filters"] = filters
    st.session_state["store_offset"] = 0
offset = st.session_state.get("store_offset", 0)

params = {
    "sort_by": SORT_OPTIONS[sort_label],
    "order": order,
    "limit": PAGE_SIZE,
    "offset": offset,
}
if q.strip():
    params["q"] = q.strip()
if status != "Any":
    params["account_status"] = status
if fraud_band != "Any":
    params["fraud_band"] = fraud_band
if default_band != "Any":
    params["default_band"] = default_band
if category != "Any":
    params["category"] = category
if city != "Any":
    params["city"] = city

# ---------- List ----------

try:
    page = api_client.get("/stores", params=params)
except ApiError as err:
    st.error(err.message)
    st.stop()

items = page["items"]
total = page["total"]

if items:
    table = style_bands(
        pd.DataFrame([flatten_store(s) for s in items]),
        ["Fraud band", "Default band"],
    )
    event = st.dataframe(
        table,
        on_select="rerun",
        selection_mode="single-row",
        key="stores_table",
    )
    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        st.session_state["selected_store_id"] = items[selected_rows[0]]["id"]
else:
    st.info("No stores match these filters.")

# Pagination
b1, b2, b3 = st.columns([1, 3, 1])
if b1.button("Previous", key="store_prev", disabled=offset == 0):
    st.session_state["store_offset"] = max(0, offset - PAGE_SIZE)
    st.rerun()

if total:
    b2.caption(f"Showing {offset + 1}–{offset + len(items)} of {total}")

if b3.button("Next", key="store_next", disabled=offset + PAGE_SIZE >= total):
    st.session_state["store_offset"] = offset + PAGE_SIZE
    st.rerun()

# ---------- Profile ----------

st.divider()
selected_id = st.session_state.get("selected_store_id")
if selected_id is None:
    st.info("Select a row in the table to view the store profile.")
    st.stop()

try:
    store = api_client.get(f"/stores/{selected_id}")
except ApiError as err:
    st.error(err.message)
    st.stop()

show_feedback()

st.subheader(f"{store['name']} (ID {store['id']})")
st.caption(
    f"Registration {store['commercial_registration_no']}  ·  "
    f"{store['category']}  ·  {store['city']}  ·  "
    f"Status: {store['account_status']}  ·  Created {fmt_date(store['created_at'])}"
)

scores = store.get("scores")
if scores is None:
    st.info("Store risk scoring is not built yet. This store has no risk score.")
    #st.warning("No risk score available for this store.")
else:
    m1, m2 = st.columns(2)
    with m1:
        st.markdown("**Fraud risk**")
        st.metric("Score (0–100)", fmt_score(scores["fraud_score"]))
        st.markdown(band_badge(scores["fraud_band"]), unsafe_allow_html=True)
    with m2:
        st.markdown("**Default risk**")
        st.metric("Default percentile (0–100)", fmt_score(scores["default_score"]))
        st.markdown(band_badge(scores["default_band"]), unsafe_allow_html=True)

    st.caption(
        f"Model {scores['model_version']}  ·  computed {fmt_date(scores['computed_at'])}"
    )
    if scores["model_version"].startswith("placeholder"):
        st.warning("These scores are random placeholders, not model output.")

    factors = scores.get("top_factors")
    if factors:
        st.markdown("**Top factors**")
        st.json(factors)
    else:
        st.caption("No explanations yet (top factors are filled by the scoring job).")

st.divider()
render_score_history("store", store["id"])
st.divider()
st.markdown("**Deal statistics**")
stats = store["stats"]
s1, s2, s3, s4, s5 = st.columns(5)
s1.metric("Total deals", f"{stats['total_deals']:,}")
s2.metric("Disputed deals", f"{stats['disputed_deals']:,}")
s3.metric("Dispute rate", fmt_rate(stats["dispute_rate"]))
s4.metric("Refunded deals", f"{stats['refunded_deals']:,}")
s5.metric("Refund rate", fmt_rate(stats["refund_rate"]))
st.caption(
    f"Refund rate = refunded deals / {stats['paid_deals']:,} deals with a payment record."
)
st.caption(
    "Delivery failures: not shown yet. Shipment data exists, but the API does not return it yet."
    #"Delivery failures: not available. The data does not record them yet."
)
st.divider()
render_actions(f"/stores/{store['id']}", STORE_ACTIONS)

st.divider()
render_note_form(f"/stores/{store['id']}")

st.divider()
st.markdown("**Recent deals**")
deals = store.get("recent_deals", [])
if deals:
    st.dataframe(
        pd.DataFrame([
            {
                "Deal ID": d["id"],
                "Customer ID": d["customer_id"],
                "Amount": fmt_money(d["amount_sar"]),
                "Status": d["status"],
                "Created": fmt_date(d["created_at"]),
                "Closed": fmt_date(d["closed_at"]),
            }
            for d in deals
        ]),
        hide_index=True,
    )
else:
    st.caption("No deals for this store.")

st.divider()
render_history(f"/stores/{store['id']}")

st.divider()
render_transaction_timeline(f"/stores/{store['id']}")