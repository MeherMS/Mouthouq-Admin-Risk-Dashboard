import api_client
import pandas as pd
import streamlit as st
from api_client import ApiError
import plotly.express as px

from config import BAND_COLORS

BAND_OPTIONS = ["Any", "low", "medium", "high"]

# Temporary identities (Phase 3, section 4.7). IDs confirmed from seed_users.py.
ADMIN_CHOICES = {
    "Admin (id 1)": {"id": "1", "role": "admin"},
    "Viewer (id 2)": {"id": "2", "role": "viewer"},
}

FEEDBACK_KEY = "action_feedback"

# (button label, endpoint suffix, success message)
CUSTOMER_ACTIONS = [
    ("Freeze account", "freeze", "Account frozen."),
    ("Unfreeze account", "unfreeze", "Account unfrozen."),
    ("Flag for review", "flag-review", "Flagged for review."),
]


def render_sidebar() -> None:
    """Shared sidebar. Call at the top of every page."""
    st.sidebar.title("Admin Risk Dashboard")
    label = st.sidebar.selectbox("Acting as", list(ADMIN_CHOICES), index=0)
    identity = ADMIN_CHOICES[label]
    st.session_state["admin_id"] = identity["id"]
    st.session_state["admin_role"] = identity["role"]
    st.sidebar.caption("Temporary identity. Replaced by real login later.")


def is_admin() -> bool:
    return st.session_state.get("admin_role") == "admin"


def band_badge(band: str | None) -> str:
    """HTML badge for a risk band. Use with st.markdown(..., unsafe_allow_html=True)."""
    if not band:
        return "—"
    color = BAND_COLORS.get(band, "#616161")
    return (
        f'<span style="background:{color};color:white;'
        f'padding:2px 10px;border-radius:4px;">{band.title()}</span>'
    )


def fmt_score(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def fmt_date(value: str | None) -> str:
    if not value:
        return "—"
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def fmt_money(value: float | None) -> str:
    return "—" if value is None else f"SAR {value:,.2f}"




def show_feedback() -> None:
    """Show the result of the last action once, then clear it."""
    feedback = st.session_state.pop(FEEDBACK_KEY, None)
    if feedback:
        kind, text = feedback
        getattr(st, kind)(text)


NOTE_MAX_CHARS = 2000


ACTION_LABELS = {
    "freeze": "Freeze",
    "unfreeze": "Unfreeze",
    "approve": "Approve",
    "reject": "Reject",
    "flag_review": "Flag for review",
    "add_note": "Note",
}


def _fmt_timestamp(value: str | None) -> str:
    if not value:
        return "—"
    return pd.to_datetime(value).strftime("%Y-%m-%d %H:%M")


def render_history(entity_path: str, limit: int = 50) -> None:
    """
    Recent actions and notes for one customer or store, newest first.
    entity_path example: "/customers/12"
    """
    st.markdown("**Action history**")
    try:
        page = api_client.get(f"{entity_path}/actions", params={"limit": limit})
    except ApiError as err:
        st.error(err.message)
        return

    items = page["items"]
    if not items:
        st.caption("No actions or notes recorded for this record yet.")
        return

    st.dataframe(
        pd.DataFrame([
            {
                "When": _fmt_timestamp(a["created_at"]),
                "Action": ACTION_LABELS.get(a["action_type"], a["action_type"]),
                "Admin ID": a["admin_id"],
                "Reason / note": a["reason"],
            }
            for a in items
        ]),
        hide_index=True,
    )

    if page["total"] > len(items):
        st.caption(
            f"Showing the {len(items)} most recent of {page['total']}. "
            "The full history is in the Action log."
        )

def render_score_history(entity_type: str, entity_id: int) -> None:
    """
    Fraud and default score over time for one customer or store.
    entity_type is "customer" or "store".
    """
    st.markdown("**Score history**")
    try:
        history = api_client.get(f"/scores/history/{entity_type}/{entity_id}")
    except ApiError as err:
        st.error(err.message)
        return

    points = history["points"]
    if not points:
        st.caption("No score history yet.")
        return

    df = pd.DataFrame(points)
    df["computed_at"] = pd.to_datetime(df["computed_at"], format="ISO8601", errors="coerce")

    long = df.melt(
        id_vars=["computed_at", "model_version"],
        value_vars=["fraud_score", "default_score"],
        var_name="Risk",
        value_name="Score",
    )
    long["Risk"] = long["Risk"].map({"fraud_score": "Fraud", "default_score": "Default"})

    fig = px.line(
        long,
        x="computed_at",
        y="Score",
        color="Risk",
        markers=True,
        hover_data=["model_version"],
        labels={"computed_at": "Computed at"},
    )
    fig.update_yaxes(range=[0, 100])
    fig.add_hline(
        y=40, line_dash="dot", line_color=BAND_COLORS["medium"],
        annotation_text="Medium (40)", annotation_position="top left",
    )
    fig.add_hline(
        y=70, line_dash="dot", line_color=BAND_COLORS["high"],
        annotation_text="High (70)", annotation_position="top left",
    )
    st.plotly_chart(fig, use_container_width=True)

    if len(points) == 1:
        st.caption("One score run so far, so the chart shows a single point.")

    if any(p["model_version"].startswith("placeholder") for p in points):
        st.warning("These historical scores are random placeholders, not model output.")


PENDING_KEY = "pending_action"


def _run_action(path: str, reason: str, success_text: str, clear_keys: list[str]) -> None:
    """Send the action to the API. Called only after the admin confirms."""
    try:
        result = api_client.post(
            path,
            st.session_state.get("admin_id"),
            {"reason": reason.strip()},
        )
    except ApiError as err:
        st.error(err.message)
        return

    # Phase 3 returns changed: false for idempotent no-ops.
    if result.get("changed", True):
        st.session_state[FEEDBACK_KEY] = ("success", success_text)
    else:
        st.session_state[FEEDBACK_KEY] = ("info", "No change: the record is already in that state.")

    # Clear the reason box only after a successful request.
    for key in clear_keys:
        st.session_state.pop(key, None)
    st.rerun()


def _request_action(
    pending_key: str,
    path: str,
    reason: str,
    label: str,
    success_text: str,
    clear_keys: list[str],
) -> None:
    """Validate the reason and store the request. Nothing is sent yet."""
    if len(reason.strip()) < 3:
        st.warning("The reason must be at least 3 characters.")
        return
    # Only one request can be pending at a time.
    st.session_state[PENDING_KEY] = {
        "key": pending_key,
        "path": path,
        "reason": reason.strip(),
        "label": label,
        "success": success_text,
        "clear_keys": clear_keys,
    }


def _confirm_block(pending_key: str) -> None:
    """Shows the confirmation for this action, if one is pending."""
    pending = st.session_state.get(PENDING_KEY)
    if not pending or pending["key"] != pending_key:
        return

    st.warning(
        f"**Confirm: {pending['label']}?**\n\n"
        f"Reason: {pending['reason']}\n\n"
        "This is recorded in the action log and the audit trail."
    )
    c1, c2 = st.columns(2)
    if c1.button(
        "Yes, confirm",
        key=f"confirm_{pending_key}",
        type="primary",
        disabled=not is_admin(),
    ):
        st.session_state.pop(PENDING_KEY, None)
        _run_action(pending["path"], pending["reason"], pending["success"], pending["clear_keys"])
    if c2.button("Cancel", key=f"cancel_{pending_key}"):
        st.session_state.pop(PENDING_KEY, None)
        st.rerun()


def render_actions(entity_path: str, actions: list[tuple[str, str, str]]) -> None:
    """
    One expander per action. Review -> confirm. Nothing runs without confirmation.
    entity_path example: "/customers/12"
    """
    st.markdown("**Admin actions**")
    if not is_admin():
        st.caption("Viewer role cannot change records. Switch to Admin in the sidebar.")

    cols = st.columns(len(actions))
    for col, (label, suffix, success_text) in zip(cols, actions):
        key = f"{entity_path}/{suffix}"
        reason_key = f"reason_{key}"
        with col.expander(label):
            st.text_area(
                "Reason (required, at least 3 characters)",
                key=reason_key,
            )
            if st.button(f"Review: {label}", key=f"review_{key}", disabled=not is_admin()):
                _request_action(
                    key, key, st.session_state.get(reason_key, ""),
                    label, success_text, clear_keys=[reason_key],
                )
            _confirm_block(key)


def render_note_form(entity_path: str) -> None:
    """
    Free-text note with the same review and confirm steps as other actions.
    Sent as the 'reason' field, because ReasonBody has no separate note field.
    """
    st.markdown("**Add a note**")
    if not is_admin():
        st.caption("Viewer role cannot add notes. Switch to Admin in the sidebar.")

    key = f"{entity_path}/notes"
    note_key = f"note_{entity_path}"
    st.text_area(
        f"Note (at least 3 characters, max {NOTE_MAX_CHARS})",
        key=note_key,
        max_chars=NOTE_MAX_CHARS,
    )
    if st.button("Review note", key=f"review_{key}", disabled=not is_admin()):
        _request_action(
            key, key, st.session_state.get(note_key, ""),
            "Add note", "Note saved.", clear_keys=[note_key],
        )
    _confirm_block(key)




UNSCORED_COLOR = "#9e9e9e"


def style_bands(df: pd.DataFrame, columns: list[str]):
    """
    Colors band cells with the same colors as the profile badges.
    Use the result with st.dataframe. Do not also pass hide_index.
    """
    def _css(value) -> str:
        color = BAND_COLORS.get(str(value).lower())
        if color is None:
            return ""
        return f"background-color: {color}; color: white; font-weight: 600"

    return df.style.map(_css, subset=columns).hide(axis="index")

def render_transaction_timeline(entity_path: str, limit: int = 50) -> None:
    """
    Transactions (table) and their payment events (timeline chart).
    entity_path example: "/customers/12"
    """
    st.markdown("**Transactions and payment timeline**")
    try:
        page = api_client.get(f"{entity_path}/transactions", params={"limit": limit})
    except ApiError as err:
        st.error(err.message)
        return

    items = page["items"]
    if not items:
        st.caption("No transactions recorded for this record yet.")
        return

    rows = []
    event_rows = []
    for t in items:
        rows.append({
            "When": pd.to_datetime(t["timestamp"]).strftime("%Y-%m-%d %H:%M"),
            "Transaction ID": t["id"],
            "Deal ID": t["deal_id"],
            "Amount": fmt_money(t["amount_sar"]),
            "Method": t["method"].replace("_", " ").title(),
            "Status": t["status"].replace("_", " ").title(),
            "Failure reason": t["failure_reason"] or "—",
            "Payment events": len(t["events"]),
        })
        for e in t["events"]:
            event_rows.append({
                "Transaction": f"#{t['id']}",
                "Occurred": pd.to_datetime(e["occurred_at"]),
                "Event": e["event_type"].replace("_", " ").title(),
            })

    st.dataframe(pd.DataFrame(rows), hide_index=True)

    if not event_rows:
        st.caption("These transactions have no payment events yet.")
        return

    events_df = pd.DataFrame(event_rows)
    # Keep transactions in the same order as the table (newest at the top).
    order = [f"#{t['id']}" for t in items]
    fig = px.scatter(
        events_df,
        x="Occurred",
        y="Transaction",
        color="Event",
        category_orders={"Transaction": list(reversed(order))},
        hover_data=["Event"],
    )
    fig.update_traces(marker=dict(size=10))
    fig.update_layout(height=max(250, 40 * len(order) + 120), yaxis_title="Transaction")
    st.plotly_chart(fig, use_container_width=True)

    if page["total"] > len(items):
        st.caption(
            f"Showing the {len(items)} most recent of {page['total']} transactions."
        )