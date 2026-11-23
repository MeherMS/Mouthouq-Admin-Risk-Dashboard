import os

import pandas as pd
import requests
import streamlit as st

from common import render_sidebar
from config import API_BASE_URL  # CONFIRM: name used in config.py

# CONFIRM: match the key name used in your secrets and api_client.py
API_KEY_NAME = "API_KEY"

render_sidebar()


def _api_key():
    try:
        return st.secrets[API_KEY_NAME]
    except Exception:
        return os.environ.get(API_KEY_NAME, "")


@st.cache_data(ttl=600, show_spinner="Reading the database structure...")
def load_overview(base_url, api_key):
    response = requests.get(
        f"{base_url}/database/overview",
        headers={"X-API-Key": api_key},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def build_dot(data):
    lines = [
        "digraph G {",
        "  rankdir=LR;",
        '  graph [bgcolor="transparent", nodesep=0.4, ranksep=1.2];',
        '  node [shape=box, style="rounded,filled", fillcolor="#EAF2FB", '
        'color="#4A6FA5", fontname="Helvetica", fontsize=11];',
        '  edge [color="#4A6FA5", fontname="Helvetica", fontsize=9];',
    ]
    for t in data["tables"]:
        lines.append(
            f'  "{t["name"]}" [label="{t["title"]}\\n{t["row_count"]:,} rows"];'
        )
    for r in data["relations"]:
        lines.append(
            f'  "{r["from_table"]}" -> "{r["to_table"]}" [label="{r["column"]}"];'
        )
    for s in data["soft_links"]:
        for target in s["targets"]:
            lines.append(
                f'  "{s["from_table"]}" -> "{target}" '
                f'[label="{s["column"]}", style=dashed, color="#999999"];'
            )
    lines.append("}")
    return "\n".join(lines)


st.title("Database Guide")
st.caption(
    "A plain-language map of what data we store, how the tables connect, "
    "and what the numbers show. This page is read-only."
)

st.info(
    "All data in this prototype is synthetic (generated for testing). "
    "Fields marked 'Synthetic only' are answer-key fields from the generator. "
    "They are labeled here but never shown with values."
)

base_url = API_BASE_URL.rstrip("/")
api_key = _api_key()

try:
    data = load_overview(base_url, api_key)
except requests.RequestException as exc:
    st.error(f"Could not load the database overview from the API: {exc}")
    st.stop()

st.caption(f"Structure read at {data['generated_at']} (UTC). Refreshes every 10 minutes.")

# ---- Summary ----
summary = data["summary"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Tables", summary["tables"])
c2.metric("Total rows", f"{summary['total_rows']:,}")
c3.metric("Links between tables", summary["relationships"])
c4.metric("Synthetic-only fields", summary["synthetic_only_fields"])

# ---- Diagram ----
st.header("How the tables connect")
st.graphviz_chart(build_dot(data), use_container_width=True)
st.caption(
    "Each arrow points from the table that holds the link to the table it refers to. "
    "Solid arrows are enforced by the database. Dashed arrows are conventions only: "
    "the database does not check them."
)

# ---- Table cards ----
st.header("The tables")
st.write("Open a table to see what each column means.")

for t in data["tables"]:
    with st.expander(f"{t['title']}  ·  {t['row_count']:,} rows"):
        st.write(t["purpose"])
        df = pd.DataFrame(t["columns"]).rename(columns={
            "field": "Column",
            "meaning": "What it means",
            "type": "Data type",
            "key": "Key role",
            "synthetic_only": "Synthetic only",
        })
        df["Synthetic only"] = df["Synthetic only"].map(
            {True: "Yes (generator only, hidden)", False: ""}
        )
        st.dataframe(df, hide_index=True, use_container_width=True)

# ---- Key numbers ----
st.header("Key numbers")
if data["headline"]:
    cols = st.columns(len(data["headline"]))
    for col, item in zip(cols, data["headline"]):
        col.metric(item["label"], item["value"])
else:
    st.write("No headline numbers available.")

# ---- Statistics ----
st.header("Patterns in the data")
st.write(
    "Counts by category. These describe what is stored, not whether any "
    "customer or store is risky."
)
for s in data["statistics"]:
    st.subheader(s["title"])
    df = pd.DataFrame(s["rows"]).set_index("label")
    left, right = st.columns([2, 3])
    with left:
        st.dataframe(df, use_container_width=True)
    with right:
        st.bar_chart(df)

# ---- Recommendations ----
st.header("What we recommend next")
st.markdown(
    """
1. **Keep the synthetic-only fields out of real data.** Remove `default_label`, `synthetic_profile`, and `is_fraud` before any real customer data is loaded.
2. **Add a devices table** if device reuse is a real fraud signal. Today, shared phone numbers stand in for it.
3. **Make the audit log add-only at the database level**, so past records cannot be changed or deleted.
4. **Log rejected admin attempts** (403, 404, 409) so the audit trail is complete.
5. **Decide on the unused predictions table.** Either remove it or document why it exists.
6. **Show when scores were last computed** on this page once the scoring job runs on a schedule.
7. **Assign one owner** who updates the descriptions here whenever the database changes.
"""
)

# ---- Glossary ----
st.header("Words used in this guide")
glossary = pd.DataFrame(
    [
        ("Customer", "A person who buys on credit through the platform."),
        ("Store", "A shop or service provider that sells through the platform."),
        ("Deal", "One purchase agreement between a customer and a store."),
        ("Transaction", "A payment attempt for a deal."),
        ("Payment event", "What happened to a payment, such as on time, late, or missed."),
        ("Risk score", "A number from 0 to 100 showing how risky a customer or store looks."),
        ("Fraud risk", "Risk that the customer intends to cheat from the start."),
        ("Default risk", "Risk that the customer wants to pay but cannot."),
        ("Band", "A risk group: Low, Medium, or High."),
        ("Percentile", "Where a customer ranks among all customers. 99 means higher risk than 99% of customers."),
        ("Synthetic data", "Made-up data generated for testing. It does not describe real people."),
    ],
    columns=["Term", "Meaning"],
)
st.dataframe(glossary, hide_index=True, use_container_width=True)