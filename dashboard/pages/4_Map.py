import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from api_client import ApiError, get
from common import render_sidebar
from config import BAND_COLORS

GRAY = "#9e9e9e"
ENTITY_LABELS = {"customer": "Customers", "store": "Stores"}
COLOR_LABELS = {"fraud_band": "Fraud band", "default_band": "Default band"}
BAND_ORDER = [
    ("high", "High"),
    ("medium", "Medium"),
    ("low", "Low"),
    (None, "Unscored"),
]

render_sidebar()
st.title("Map")
st.caption(
    "Positions are city centers with a small offset, not home or store addresses. "
    "All data is synthetic."
)


@st.cache_data(ttl=300)
def load_points(entity: str) -> dict:
    return get("/map/points", params={"entity": entity})


@st.cache_data(ttl=300)
def load_flows() -> dict:
    return get("/map/shipment-flows")


def hover_text(p: dict) -> str:
    fraud = p["fraud_band"] or "unscored"
    default = p["default_band"] or "unscored"
    return f"{p['city']}<br>Fraud band: {fraud}<br>Default band: {default}"


controls = st.columns([1, 1, 1])
with controls[0]:
    entity = st.radio(
        "Show",
        list(ENTITY_LABELS),
        format_func=ENTITY_LABELS.get,
        horizontal=True,
    )
with controls[1]:
    color_by = st.radio(
        "Color by",
        list(COLOR_LABELS),
        format_func=COLOR_LABELS.get,
        horizontal=True,
    )
with controls[2]:
    show_lines = st.checkbox("Show shipment lines", value=False)

try:
    data = load_points(entity)
    flows = load_flows()
except ApiError as e:
    st.error(e.message)
    st.stop()

points = data["points"]

if entity == "store":
    st.info("Store risk scores are not built yet, so all stores show as unscored.")

versions = {p["model_version"] for p in points if p["model_version"]}
if any(v.startswith("placeholder") for v in versions):
    st.warning(
        "These scores are placeholders. They are not model output and carry "
        "no information about real risk."
    )

fig = go.Figure()

# Shipment lines first, so the points sit on top of them.
if show_lines:
    centers = flows["city_centers"]
    max_n = max((f["shipments"] for f in flows["flows"]), default=1)
    for f in flows["flows"]:
        o = centers[f["origin_city"]]
        d = centers[f["destination_city"]]
        width = 1 + 6 * f["shipments"] / max_n
        fig.add_trace(go.Scattermap(
            lat=[o[0], d[0]],
            lon=[o[1], d[1]],
            mode="lines",
            line=dict(width=width, color="rgba(60,90,160,0.45)"),
            text=(
                f"{f['origin_city']} to {f['destination_city']}: "
                f"{f['shipments']} shipments, "
                f"first-attempt success {f['first_attempt_success_rate']:.1%}"
            ),
            hoverinfo="text",
            showlegend=False,
        ))

# Entity points, colored by the selected band.
for band, label in BAND_ORDER:
    subset = [p for p in points if p[color_by] == band]
    if not subset:
        continue
    fig.add_trace(go.Scattermap(
        lat=[p["lat"] for p in subset],
        lon=[p["lon"] for p in subset],
        mode="markers",
        marker=dict(
            size=7,
            color=BAND_COLORS.get(band, GRAY),
            opacity=0.7,
        ),
        name=f"{label} ({len(subset)})",
        text=[hover_text(p) for p in subset],
        hoverinfo="text",
    ))

fig.update_layout(
    map=dict(
        style="open-street-map",
        center=dict(lat=24.5, lon=44.5),
        zoom=5,
    ),
    margin=dict(l=0, r=0, t=40, b=0),
    height=600,
    legend=dict(orientation="h", y=1.02, x=0),
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Same-city shipments")
st.caption(
    "Shipments whose origin and destination are the same city. "
    "These are not drawn as lines."
)
if flows["same_city"]:
    same = pd.DataFrame(flows["same_city"])[[
        "origin_city", "shipments", "delivered", "first_attempt_success_rate",
    ]].rename(columns={
        "origin_city": "City",
        "shipments": "Shipments",
        "delivered": "Delivered",
        "first_attempt_success_rate": "First-attempt success",
    })
    same["First-attempt success"] = same["First-attempt success"].map(
        lambda x: f"{x:.1%}"
    )
    st.dataframe(same, hide_index=True, use_container_width=True)
else:
    st.write("No same-city shipments.")