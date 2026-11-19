import pandas as pd
import streamlit as st

import api_client
from api_client import ApiError
from common import render_sidebar

st.set_page_config(page_title="Action log", layout="wide")
render_sidebar()
st.title("Action log")
st.caption("Every admin action and note, newest first. Read-only.")

# Verify these values against EntityType and ActionType in app/models.py.
ENTITY_OPTIONS = {"Any": None, "Customer": "customer", "Store": "store"}
ACTION_OPTIONS = {
    "Any": None,
    "Freeze": "freeze",
    "Unfreeze": "unfreeze",
    "Approve": "approve",
    "Reject": "reject",
    "Flag for review": "flag_review",
    "Note": "add_note",
}
ADMIN_OPTIONS = {"Any": None, "Admin (id 1)": 1, "Viewer (id 2)": 2}

PAGE_SIZE = 50


def fmt_timestamp(value: str | None) -> str:
    if not value:
        return "—"
    return pd.to_datetime(value).strftime("%Y-%m-%d %H:%M")


# ---------- Filters ----------

f1, f2, f3, f4 = st.columns([1.5, 1.5, 1.5, 1.5])
entity_label = f1.selectbox("Entity type", list(ENTITY_OPTIONS))
action_label = f2.selectbox("Action", list(ACTION_OPTIONS))
admin_label = f3.selectbox("Admin", list(ADMIN_OPTIONS))
entity_id = f4.number_input("Entity ID (0 = any)", min_value=0, value=0, step=1)

# Reset to the first page whenever a filter changes.
filters = (entity_label, action_label, admin_label, int(entity_id))
if st.session_state.get("log_filters") != filters:
    st.session_state["log_filters"] = filters
    st.session_state["log_offset"] = 0
offset = st.session_state.get("log_offset", 0)

params = {"limit": PAGE_SIZE, "offset": offset}
if ENTITY_OPTIONS[entity_label]:
    params["entity_type"] = ENTITY_OPTIONS[entity_label]
if ACTION_OPTIONS[action_label]:
    params["action_type"] = ACTION_OPTIONS[action_label]
if ADMIN_OPTIONS[admin_label] is not None:
    params["admin_id"] = ADMIN_OPTIONS[admin_label]
if entity_id > 0:
    params["entity_id"] = int(entity_id)

# ---------- List ----------

try:
    page = api_client.get("/actions", params=params)
except ApiError as err:
    st.error(err.message)
    st.stop()

items = page["items"]
total = page["total"]

if items:
    st.dataframe(
        pd.DataFrame([
            {
                "Log ID": a["id"],
                "When": fmt_timestamp(a["created_at"]),
                "Entity": a["entity_type"].title(),
                "Entity ID": a["entity_id"],
                "Action": a["action_type"],
                "Admin ID": a["admin_id"],
                "Reason": a["reason"],
            }
            for a in items
        ]),
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("No actions match these filters.")

# ---------- Pagination ----------

b1, b2, b3 = st.columns([1, 3, 1])
if b1.button("Previous", disabled=offset == 0):
    st.session_state["log_offset"] = max(0, offset - PAGE_SIZE)
    st.rerun()

if total:
    b2.caption(f"Showing {offset + 1}–{offset + len(items)} of {total}")
else:
    b2.caption("No results")

if b3.button("Next", disabled=offset + PAGE_SIZE >= total):
    st.session_state["log_offset"] = offset + PAGE_SIZE
    st.rerun()