import pandas as pd
import plotly.express as px
import streamlit as st

import api_client
from api_client import ApiError
from common import BAND_COLORS, UNSCORED_COLOR, fmt_date, fmt_score, render_sidebar, style_bands


TOP_N = 10
st.set_page_config(page_title="Overview", layout="wide")
render_sidebar()
st.title("Overview")
#st.caption("Risk counts, trend, and the riskiest entities. Read-only.")
st.caption("Risk counts, trend, and the riskiest entities. Read-only.")
st.info(
    "Store risk scores are not built yet, so every store shows as Unscored. "
    "Default scores are percentile ranks among customers."
)

try:
    summary = api_client.get("/dashboard/summary")
except ApiError as err:
    st.error(err.message)
    st.stop()

model_version = summary.get("model_version")
if model_version is None:
    st.warning("No risk scores exist yet. Run the scoring job or the placeholder seed.")
elif model_version.startswith("placeholder"):
    st.warning("These scores are random placeholders, not model output.")
    st.caption(f"Model {model_version}  ·  computed {fmt_date(summary['computed_at'])}")
else:
    st.caption(f"Model {model_version}  ·  computed {fmt_date(summary['computed_at'])}")

# Bar colors by band. Keys match the Band labels used in the chart data.
BAND_CHART_COLORS = {
    "Low": BAND_COLORS["low"],
    "Medium": BAND_COLORS["medium"],
    "High": BAND_COLORS["high"],
    "Unscored": UNSCORED_COLOR,
}


def render_counts(block: dict) -> None:
    total = block["total"]
    fraud_high = block["fraud"]["high"]
    default_high = block["default"]["high"]

    m1, m2, m3 = st.columns(3)
    m1.metric("Total", f"{total:,}")
    m2.metric("High fraud risk", f"{fraud_high:,}")
    m3.metric("High default risk", f"{default_high:,}")

    rows = []
    for risk_key, risk_label in [("fraud", "Fraud risk"), ("default", "Default risk")]:
        for band_key, band_label in [
            ("low", "Low"),
            ("medium", "Medium"),
            ("high", "High"),
            ("unscored", "Unscored"),
        ]:
            rows.append({
                "Risk": risk_label,
                "Band": band_label,
                "Count": block[risk_key][band_key],
            })
    fig = px.bar(
        pd.DataFrame(rows),
        x="Risk",
        y="Count",
        color="Band",
        barmode="group",
        color_discrete_map=BAND_CHART_COLORS,
        category_orders={"Band": ["Low", "Medium", "High", "Unscored"]},
    )
    st.plotly_chart(fig, use_container_width=True)

def render_top(entities: list[dict], risk: str) -> None:
    """Table of the riskiest entities for one risk type."""
    if not entities:
        st.info("No scored entities yet.")
        return
    score_label = "Fraud score" if risk == "fraud" else "Default percentile"
    df = pd.DataFrame([
        {
            "Type": e["entity_type"].title(),
            "ID": e["entity_id"],
            "Name": e["name"],
            "Status": e["account_status"],
            score_label: fmt_score(e[f"{risk}_score"]),
            "Band": e[f"{risk}_band"].title(),
        }
        for e in entities
    ])
    st.dataframe(style_bands(df, ["Band"]), use_container_width=True)

tab_customers, tab_stores = st.tabs(["Customers", "Stores"])
with tab_customers:
    render_counts(summary["customers"])
with tab_stores:
    render_counts(summary["stores"])

st.divider()
st.subheader("High-risk trend")
trend = summary["trend"]
if trend:
    trend_df = pd.DataFrame(trend)
    fig = px.line(
        trend_df,
        x="date",
        y=["fraud_high", "default_high"],
        labels={"value": "High-risk scores", "date": "Date", "variable": "Risk"},
    )
    st.plotly_chart(fig, use_container_width=True)
    if len(trend) == 1:
        st.caption("Only one scoring run so far, so the trend is a single point.")
else:
    st.info("No score history yet.")

st.divider()
st.subheader(f"Top {TOP_N} by fraud score")
st.caption("Fraud scores are absolute (0 to 100). This list is ranked on fraud score only.")
render_top(summary["top_fraud"], "fraud")

st.divider()
st.subheader(f"Top {TOP_N} by default percentile")
st.caption("Percentile rank among scored customers. This list is ranked on default only.")
render_top(summary["top_default"], "default")