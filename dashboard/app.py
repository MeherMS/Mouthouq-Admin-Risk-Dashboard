import pandas as pd
import plotly.express as px
import streamlit as st

import api_client
from api_client import ApiError
from common import fmt_date, fmt_score, render_sidebar, style_bands
from theme import COLORS, header, notice, section, style_figure

TOP_N = 10

BAND_CHART_COLORS = {
    "Low": COLORS["low"],
    "Medium": COLORS["medium"],
    "High": COLORS["high"],
    "Unscored": COLORS["unscored"],
}

st.set_page_config(page_title="Overview", layout="wide")
render_sidebar()

header(
    "Overview",
    subtitle="Risk counts, trend, and the riskiest entities. Read-only.",
    eyebrow="Admin Risk Dashboard",
)

notice(
    "<strong>Stores are unscored.</strong> Store risk scores are not built yet. "
    "Default scores are percentile ranks among customers."
)

try:
    summary = api_client.get("/dashboard/summary")
except ApiError as err:
    st.error(err.message)
    st.stop()

model_version = summary.get("model_version")
if model_version is None:
    notice("<strong>No scores yet.</strong> Run the scoring job or the placeholder seed.")
else:
    if model_version.startswith("placeholder"):
        notice("<strong>Placeholder scores.</strong> These values are random, not model output.")
    st.caption(f"Model {model_version}  ·  computed {fmt_date(summary['computed_at'])}")


def render_counts(block: dict) -> None:
    """KPI cards, band distribution chart for one entity type."""
    m1, m2, m3 = st.columns(3)
    m1.metric("Total", f"{block['total']:,}")
    m2.metric("High fraud risk", f"{block['fraud']['high']:,}")
    m3.metric("High default risk", f"{block['default']['high']:,}")

    section("Risk band distribution")
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
    st.plotly_chart(style_figure(fig), use_container_width=True, config={"displayModeBar": False})


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
    st.dataframe(style_bands(df, ["Band"]), use_container_width=True, hide_index=True)


tab_customers, tab_stores = st.tabs(["Customers", "Stores"])
with tab_customers:
    render_counts(summary["customers"])
with tab_stores:
    render_counts(summary["stores"])

# st.divider()
# section("High-risk trend")
# trend = summary["trend"]
# if trend:
#     long_df = (
#         pd.DataFrame(trend)
#         .melt(
#             id_vars="date",
#             value_vars=["fraud_high", "default_high"],
#             var_name="Risk",
#             value_name="High-risk scores",
#         )
#     )
#     long_df["Risk"] = long_df["Risk"].map({"fraud_high": "Fraud", "default_high": "Default"})

#     fig = px.line(
#         long_df,
#         x="date",
#         y="High-risk scores",
#         color="Risk",
#         markers=True,
#         color_discrete_map={"Fraud": COLORS["fraud"], "Default": COLORS["default"]},
#         labels={"date": "Date"},
#     )
#     st.plotly_chart(style_figure(fig), use_container_width=True, config={"displayModeBar": False})
#     if len(trend) == 1:
#         st.caption("Only one scoring run so far, so the trend is a single point.")
# else:
#     st.info("No score history yet.")

st.divider()
section(f"Top {TOP_N} by fraud score")
st.caption("Fraud scores are absolute (0 to 100). This list is ranked on fraud score only.")
render_top(summary["top_fraud"], "fraud")

st.divider()
section(f"Top {TOP_N} by default percentile")
st.caption("Percentile rank among scored customers. This list is ranked on default only.")
render_top(summary["top_default"], "default")