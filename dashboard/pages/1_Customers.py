import pandas as pd
import streamlit as st
import json
import plotly.graph_objects as go
import api_client
from api_client import ApiError
from common import (
    BAND_OPTIONS,
    CUSTOMER_ACTIONS,
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

st.set_page_config(page_title="Customers", layout="wide")
render_sidebar()
st.title("Customers")

# Matches AccountStatus in app/models.py.
ACCOUNT_STATUS_OPTIONS = ["Any", "active", "pending", "frozen", "rejected"]

SORT_OPTIONS = {
    "Customer ID": "id",
    "Name": "name",
    "Created": "created_at",
    "Fraud score": "fraud_score",
    "Default score": "default_score",
}
PAGE_SIZE = 50

def render_top_factors(raw):
    if not raw:
        st.caption("No factors available yet.")
        return

    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        st.caption("No factors available yet.")
        return

    default_items = data.get("default", [])
    fraud_items = data.get("fraud", [])

    st.markdown("**Default risk drivers**")
    if default_items:
        names = [f["factor"] for f in default_items][::-1]
        values = [f["log_odds_contribution"] for f in default_items][::-1]
        fig = go.Figure(go.Bar(x=values, y=names, orientation="h", marker_color="#d9534f"))
        fig.update_layout(
            height=220,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_title="Log-odds contribution (higher = more risk)",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("No default factors above zero.")

    if fraud_items:
        st.markdown("**Fraud rules triggered**")
        for f in fraud_items:
            st.write(f"- {f['detail']} ({f['points']} points)")
    else:
        st.caption("No fraud rules triggered.")

def flatten_customer(c: dict) -> dict:
    s = c.get("scores") or {}
    return {
        "ID": c["id"],
        "Name": c["name"],
        "Phone": c["phone"],
        "Email": c["email"],
        "Status": c["account_status"],
        "Fraud score": s.get("fraud_score"),
        "Fraud band": s.get("fraud_band"),
        "Default score": s.get("default_score"),
        "Default band": s.get("default_band"),
        "Model": s.get("model_version") or "—",
        "Created": fmt_date(c["created_at"]),
    }
# ---------- Filters ----------

c1, c2, c3, c4 = st.columns([3, 1.5, 1.5, 1.5])
q = c1.text_input("Search name, phone or email")
status = c2.selectbox("Account status", ACCOUNT_STATUS_OPTIONS)
fraud_band = c3.selectbox("Fraud band", BAND_OPTIONS)
default_band = c4.selectbox("Default band", BAND_OPTIONS)

c5, c6 = st.columns([2, 1])
sort_label = c5.selectbox("Sort by", list(SORT_OPTIONS), index=0)
order = c6.selectbox("Order", ["asc", "desc"], index=0)

# Reset to the first page whenever a filter or sort changes.
filters = (q, status, fraud_band, default_band, sort_label, order)
if st.session_state.get("cust_filters") != filters:
    st.session_state["cust_filters"] = filters
    st.session_state["cust_offset"] = 0
offset = st.session_state.get("cust_offset", 0)

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

# ---------- List ----------

try:
    page = api_client.get("/customers", params=params)
except ApiError as err:
    st.error(err.message)
    st.stop()

items = page["items"]
total = page["total"]

if items:
    table = style_bands(
        pd.DataFrame([flatten_customer(c) for c in items]),
        ["Fraud band", "Default band"],
    )
    event = st.dataframe(
        table,
        on_select="rerun",
        selection_mode="single-row",
        key="customers_table",
    )
    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        st.session_state["selected_customer_id"] = items[selected_rows[0]]["id"]
else:
    st.info("No customers match these filters.")

# Pagination
b1, b2, b3 = st.columns([1, 3, 1])
if b1.button("Previous", disabled=offset == 0):
    st.session_state["cust_offset"] = max(0, offset - PAGE_SIZE)
    st.rerun()

if total:
    b2.caption(f"Showing {offset + 1}–{offset + len(items)} of {total}")

if b3.button("Next", disabled=offset + PAGE_SIZE >= total):
    st.session_state["cust_offset"] = offset + PAGE_SIZE
    st.rerun()

# ---------- Profile ----------

st.divider()
selected_id = st.session_state.get("selected_customer_id")
if selected_id is None:
    st.info("Select a row in the table to view the customer profile.")
    st.stop()

try:
    cust = api_client.get(f"/customers/{selected_id}")
except ApiError as err:
    st.error(err.message)
    st.stop()

show_feedback()

st.subheader(f"{cust['name']} (ID {cust['id']})")
st.caption(
    f"Phone {cust['phone']}  ·  {cust['email']}  ·  "
    f"Status: {cust['account_status']}  ·  Created {fmt_date(cust['created_at'])}"
)

scores = cust.get("scores")
if scores is None:
    st.warning("No risk score available for this customer.")
else:
    m1, m2 = st.columns(2)
    with m1:
        st.markdown("**Fraud risk**")
        st.metric("Score (0–100)", fmt_score(scores["fraud_score"]))
        st.markdown(band_badge(scores["fraud_band"]), unsafe_allow_html=True)
    with m2:
        st.markdown("**Default risk**")
        st.metric("Score (0–100)", fmt_score(scores["default_score"]))
        st.markdown(band_badge(scores["default_band"]), unsafe_allow_html=True)

    st.caption(
        f"Model {scores['model_version']}  ·  computed {fmt_date(scores['computed_at'])}"
    )
    if scores["model_version"].startswith("placeholder"):
        st.warning("These scores are random placeholders, not model output.")

    factors = scores.get("top_factors")
    render_top_factors(factors)
    if factors:
        st.markdown("**Top factors**")
        st.json(factors)
    else:
        st.caption("No explanations yet (top factors are filled by the scoring job).")

st.divider()
render_score_history("customer", cust["id"])
st.divider()
render_actions(f"/customers/{cust['id']}", CUSTOMER_ACTIONS)

st.divider()
render_note_form(f"/customers/{cust['id']}")

st.divider()
st.markdown("**Recent deals**")
deals = cust.get("recent_deals", [])
if deals:
    st.dataframe(
        pd.DataFrame([
            {
                "Deal ID": d["id"],
                "Store": d["store_name"],
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
    st.caption("No deals for this customer.")


st.divider()
render_history(f"/customers/{cust['id']}")

st.divider()
render_transaction_timeline(f"/customers/{cust['id']}")