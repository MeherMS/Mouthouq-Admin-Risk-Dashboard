"""Visual theme for the admin dashboard.

Navy, slate, and blue palette. Risk bands keep semantic colors
(green, amber, red) so they stay readable at a glance.
Keep all visual decisions here so pages stay free of styling code.
"""
import streamlit as st

COLORS = {
    "bg": "#0A1628",          # deep navy, page background
    "surface": "#111E36",     # cards, sidebar
    "surface-2": "#18294A",   # hover, buttons, tooltips
    "border": "#22365C",
    "text": "#E2E8F0",        # slate 200
    "muted": "#94A3B8",       # slate 400
    "accent": "#3B82F6",      # blue 500
    "accent-strong": "#1E40AF",  # deep blue, pressed states
    "low": "#34D399",         # band colors, semantic
    "medium": "#FBBF24",
    "high": "#F87171",
    "unscored": "#64748B",    # slate 500
    "fraud": "#A5B4FC",       # indigo 300, trend lines
    "default": "#7DD3FC",     # sky 300, trend lines
}

_STATIC_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stApp {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
}
.stApp { background: var(--bg); }
#MainMenu, footer { visibility: hidden; }

.block-container {
    padding-top: 2rem;
    padding-bottom: 4rem;
    max-width: 1280px;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: var(--surface);
    border-right: 1px solid var(--border);
}

/* Headings */
h1, h2, h3 { letter-spacing: -0.02em; color: var(--text); }
h1 { font-weight: 800; }
h2, h3 { font-weight: 700; }

/* Metric cards */
[data-testid="stMetric"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 16px 18px;
    transition: border-color 0.15s ease;
}
[data-testid="stMetric"]:hover { border-color: var(--accent); }
[data-testid="stMetricLabel"] p {
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
[data-testid="stMetricValue"] {
    font-weight: 700;
    color: var(--text);
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    border-bottom: 1px solid var(--border);
}
.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: var(--muted);
    font-weight: 600;
    padding: 8px 14px;
}
.stTabs [aria-selected="true"] { color: var(--accent) !important; }
.stTabs [data-baseweb="tab-highlight"] { background-color: var(--accent) !important; }

/* Buttons */
.stButton > button {
    border-radius: 10px;
    border: 1px solid var(--border);
    background: var(--surface-2);
    color: var(--text);
    font-weight: 600;
    transition: all 0.15s ease;
}
.stButton > button:hover {
    border-color: var(--accent);
    color: var(--accent);
}
.stButton > button[kind="primary"] {
    background: var(--accent);
    border: none;
    color: #FFFFFF;
}
.stButton > button[kind="primary"]:hover {
    background: var(--accent-strong);
    color: #FFFFFF;
}

/* Inputs */
[data-baseweb="input"], [data-baseweb="select"] > div, textarea {
    border-radius: 10px !important;
    background: var(--surface) !important;
}

/* Dataframes */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
}

/* Expanders */
[data-testid="stExpander"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
}

/* Custom components */
.app-header { margin-bottom: 1.5rem; }
.app-header .eyebrow {
    color: var(--accent);
    font-size: 2rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    margin-bottom: 0.35rem;
}
.app-header h1 {
    margin: 0;
    font-size: 2rem;
}
.app-header .subtitle {
    color: var(--muted);
    font-size: 0.95rem;
    margin-top: 0.4rem;
}

.pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    white-space: nowrap;
}

.notice {
    border-left: 3px solid var(--medium);
    background: rgba(251, 191, 36, 0.08);
    color: var(--text);
    padding: 10px 14px;
    border-radius: 10px;
    font-size: 0.9rem;
    margin: 0.5rem 0 1rem 0;
}
.notice strong { color: var(--medium); }

.section-title {
    color: var(--text);
    font-size: 1.05rem;
    font-weight: 700;
    margin: 1.5rem 0 0.75rem 0;
}

/* Score cards */
.score-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 18px 20px;
    height: 100%;
}
.score-title {
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.score-value {
    color: var(--text);
    font-size: 2.2rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    margin: 0.25rem 0 0.5rem 0;
}
.score-note {
    color: var(--muted);
    font-size: 0.82rem;
    line-height: 1.45;
    margin-top: 0.6rem;
}

/* Sidebar nav: always open on desktop, styled as an app menu */
@media (min-width: 992px) {
    [data-testid="stSidebar"] {
        min-width: 260px !important;
        max-width: 260px !important;
        transform: none !important;
        visibility: visible !important;
    }
    /* Hide the collapse and reopen controls so the sidebar stays open */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"] {
        display: none !important;
    }
    /* Keep the content from shifting when the sidebar would otherwise close */
    [data-testid="stSidebar"][aria-expanded="false"] {
        margin-left: 0 !important;
    }
}

[data-testid="stSidebarNav"] {
    padding: 0.75rem 0 0.5rem 0;
}
[data-testid="stSidebarNavItems"] {
    padding: 0 0.5rem;
}
[data-testid="stSidebarNavLink"] {
    border-radius: 10px;
    padding: 0.55rem 0.85rem;
    margin: 2px 0;
    color: var(--muted) !important;
    font-weight: 600;
    font-size: 0.95rem;
    transition: background 0.15s ease, color 0.15s ease;
    text-decoration: none;
}
[data-testid="stSidebarNavLink"]:hover {
    background: var(--surface-2);
    color: var(--text) !important;
}
[data-testid="stSidebarNavLink"][aria-current="page"],
[data-testid="stSidebarNavLink"].active {
    background: rgba(59, 130, 246, 0.16);
    color: var(--accent) !important;
}
[data-testid="stSidebarNavLink"] span {
    color: inherit !important;
}
"""


def _root_vars() -> str:
    lines = [f"--{key}: {value};" for key, value in COLORS.items()]
    return ":root {\n    " + "\n    ".join(lines) + "\n}\n"


def inject_theme() -> None:
    """Inject the theme CSS. Call once per page run, after st.set_page_config."""
    st.markdown(f"<style>{_root_vars()}{_STATIC_CSS}</style>", unsafe_allow_html=True)


def header(title: str, subtitle: str | None = None, eyebrow: str | None = None) -> None:
    """Page header with an optional eyebrow label and subtitle."""
    eyebrow_html = f'<div class="eyebrow">{eyebrow}</div>' if eyebrow else ""
    subtitle_html = f'<div class="subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="app-header">{eyebrow_html}<h1>{title}</h1>{subtitle_html}</div>',
        unsafe_allow_html=True,
    )


def section(title: str) -> None:
    """Section title with consistent spacing."""
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)


def band_pill(band: str | None) -> str:
    """Return HTML for a colored band pill. Use inside st.markdown(unsafe_allow_html=True)."""
    key = (band or "unscored").lower()
    color = COLORS.get(key, COLORS["unscored"])
    label = key.title() if band else "Unscored"
    return (
        f'<span class="pill" style="background:{color}22;color:{color};'
        f'border:1px solid {color}55">{label}</span>'
    )


def notice(text: str) -> None:
    """Amber notice box, for placeholder warnings and known limits."""
    st.markdown(f'<div class="notice">{text}</div>', unsafe_allow_html=True)


def style_figure(fig):
    """Apply the dashboard look to any Plotly figure. Returns the figure."""
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=COLORS["muted"], size=12),
        margin=dict(l=8, r=8, t=48, b=8),
        legend=dict(orientation="h", y=1.12, x=0, title_text=""),
        hoverlabel=dict(bgcolor=COLORS["surface-2"], bordercolor=COLORS["border"]),
    )
    fig.update_xaxes(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"], linecolor=COLORS["border"])
    fig.update_yaxes(gridcolor=COLORS["border"], zerolinecolor=COLORS["border"], linecolor=COLORS["border"])
    return fig


def score_card(title: str, value: str, band: str | None, note: str) -> None:
    """Score card with a label, big value, band pill, and explanatory note."""
    st.markdown(
        f'<div class="score-card">'
        f'<div class="score-title">{title}</div>'
        f'<div class="score-value">{value}</div>'
        f'<div>{band_pill(band)}</div>'
        f'<div class="score-note">{note}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )