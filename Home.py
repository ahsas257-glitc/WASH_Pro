from __future__ import annotations

import base64
import re
from pathlib import Path

import streamlit as st

from src.config import GOOGLE_SHEET_ID, TPM_COL, TOOLS
from src.data_processing import fetch_tpm_ids


# ============================================================
# Page config (MUST BE FIRST Streamlit call)
# ============================================================
st.set_page_config(page_title="WASH Pro — Home", layout="wide")


# ============================================================
# Project root (Home.py is in ROOT)
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parent
PAGES_DIR = PROJECT_ROOT / "pages"


# ============================================================
# Global Background / Liquid Glass Design (YOUR DESIGN)
# ============================================================
def _b64_image(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("utf-8")


def apply_global_background(
    logo_path: str = "assets/images/Logo_of_PPC.png",
    logo_opacity_light: float = 0.08,
    logo_opacity_dark: float = 0.15,
    intensity: float = 1.0,
) -> None:
    logo_layer = ""
    p = Path(logo_path)

    if p.exists():
        try:
            b64_logo = _b64_image(str(p))
            logo_layer = f"""
            .stApp::before {{
                content: "";
                position: fixed;
                inset: 0;
                z-index: 0;
                background: url("data:image/png;base64,{b64_logo}") center/contain no-repeat;
                opacity: var(--logo-opacity);
                filter: var(--logo-filter);
                pointer-events: none;
                animation: bgLogoFloat 30s ease-in-out infinite;
            }}
            """
        except Exception as e:
            st.warning(f"⚠️ Logo could not be loaded: {e}")
    else:
        st.warning("⚠️ Logo file not found. Check `logo_path`.")

    css = f"""
    <style>
    html, body, .stApp {{
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
        font-family: "Segoe UI", sans-serif;
    }}

    html {{
        --font-base: 22px;
        --font-label: 1rem;
        --font-h1: 2.4rem;
        --font-h2: 1.9rem;
        --font-h3: 1.5rem;
    }}

    body, .stApp {{
        font-size: var(--font-base);
        line-height: 1.7;
    }}

    .stMarkdown, .stText, .stCaption, .stMarkdown p {{
        font-size: var(--font-base);
        line-height: 1.9;
    }}

    label, .stTextInput label {{
        font-size: var(--font-label);
    }}

    input, textarea, select {{
        font-size: var(--font-base);
    }}

    .stMarkdown h1 {{ font-size: var(--font-h1) !important; }}
    .stMarkdown h2 {{ font-size: var(--font-h2) !important; }}
    .stMarkdown h3 {{ font-size: var(--font-h3) !important; }}

    @media (max-width: 768px) {{
        html {{
            --font-base: 14px;
            --font-h1: 1.8rem;
            --font-h2: 1.4rem;
            --font-h3: 1.2rem;
        }}
    }}

    footer {{ visibility: hidden; }}
    footer:after {{
        content: "Made by Shabeer Ahmad Ahsas";
        visibility: visible;
        display: block;
        text-align: center;
        font-size: 1.1rem;
        color: #409C9B;
        padding: 15px;
        opacity: .9;
    }}

    .block-container {{
        padding: 2rem 1rem !important;
        max-width: 960px;
        margin: auto;
        position: relative;
        z-index: 2;
    }}

    .stApp {{
        background: var(--base-bg);
        overflow-x: hidden;
    }}

    .stApp::after {{
        content: "";
        position: fixed;
        inset: 0;
        z-index: -1;
        background:
            radial-gradient(800px 700px at 30% 20%, rgba(var(--c1),0.25), transparent 60%),
            radial-gradient(800px 650px at 80% 30%, rgba(var(--c2),0.2), transparent 58%);
        filter: blur(30px);
        opacity: {intensity};
        pointer-events: none;
    }}

    section[data-testid="stSidebar"],
    .main > div,
    div[data-testid="stExpander"],
    div[data-testid="stContainer"],
    div[data-testid="stVerticalBlock"] > div {{
        background: var(--card-bg) !important;
        border-radius: 16px;
        border: 1px solid var(--card-border);
        box-shadow: var(--card-shadow);
        padding: 1.25rem;
        margin-bottom: 1.25rem;
        backdrop-filter: blur(14px) saturate(1.1);
        -webkit-backdrop-filter: blur(14px) saturate(1.1);
        animation: fadeInUp 0.7s ease-out forwards;
        will-change: transform, opacity;
        opacity: 0;
    }}

    @keyframes fadeInUp {{
        0% {{ transform: translateY(18px); opacity: 0; }}
        100% {{ transform: translateY(0); opacity: 1; }}
    }}

    @keyframes bgLogoFloat {{
        0% {{ transform: scale(1.05) rotate(0deg); }}
        50% {{ transform: scale(1.0) rotate(0.9deg); }}
        100% {{ transform: scale(1.05) rotate(0deg); }}
    }}

    button {{
        background: var(--btn-bg) !important;
        color: var(--btn-color) !important;
        border: none !important;
        border-radius: 12px !important;
        padding: .7rem 1.2rem !important;
        font-weight: 800 !important;
        transition: transform .2s ease-in-out, filter .2s ease-in-out;
        font-size: var(--font-base);
    }}

    button:hover {{
        transform: scale(1.02);
        filter: brightness(1.05);
        box-shadow: 0px 6px 16px rgba(0,0,0,0.2);
    }}

    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea {{
        color: var(--text-primary) !important;
        caret-color: var(--text-primary) !important;
    }}

    div[data-baseweb="input"] input::placeholder,
    div[data-baseweb="textarea"] textarea::placeholder {{
        opacity: .65 !important;
    }}

    html[data-theme="dark"] {{
        --base-bg: linear-gradient(180deg, #02030a, #0b0c12);
        --c1: 60,160,255;
        --c2: 255,120,50;

        --card-bg: rgba(12,13,27,0.45);
        --card-border: rgba(255,255,255,0.12);
        --card-shadow: 0 14px 40px rgba(0,0,0,0.6);

        --text-primary: #e5e9f0;
        --btn-bg: #2e74e1;
        --btn-color: #fafafa;

        --logo-opacity: {logo_opacity_dark};
        --logo-filter: brightness(1.15) contrast(1.1);
    }}

    html[data-theme="light"] {{
        --base-bg: linear-gradient(180deg, #eef2f7, #dfe6f2);
        --c1: 40,130,255;
        --c2: 255,140,55;

        --card-bg: rgba(255,255,255,0.6);
        --card-border: rgba(200,200,210,0.35);
        --card-shadow: 0 12px 24px rgba(0,0,0,0.1);

        --text-primary: #222;
        --btn-bg: #1f78d1;
        --btn-color: #fff;

        --logo-opacity: {logo_opacity_light};
        --logo-filter: brightness(1.25) contrast(1.05);
    }}

    {logo_layer}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


apply_global_background(
    logo_path="assets/images/Logo_of_PPC.png",
    logo_opacity_light=0.08,
    logo_opacity_dark=0.15,
    intensity=1.0,
)


# ============================================================
# Cached loader (FAST) — SAME LOGIC: ids depend on selected Tool(tab)
# ============================================================
@st.cache_data(ttl=600, show_spinner=False)
def load_tpm_ids_cached(sheet_id: str, tool_name: str, tpm_col: str) -> list[str]:
    # ✅ Same logic: TPMs only for selected worksheet_name (= tool_name)
    return fetch_tpm_ids(sheet_id, tool_name, tpm_col=tpm_col, header_row=1)


def _safe_load_tpm_ids(tool_name: str) -> tuple[list[str], str | None]:
    try:
        ids = load_tpm_ids_cached(GOOGLE_SHEET_ID, tool_name, TPM_COL)
        ids = [str(x).strip() for x in ids if str(x).strip()]
        return ids, None
    except Exception:
        return [], "Failed to load TPM list. Please check Google Sheets access and configuration."


# ============================================================
# Session defaults
# ============================================================
if "selected_tool" not in st.session_state:
    st.session_state["selected_tool"] = "Tool 6" if "Tool 6" in TOOLS else (TOOLS[0] if TOOLS else "")

if "tpm_id" not in st.session_state:
    st.session_state["tpm_id"] = ""


# ============================================================
# Resolver: YOUR real pages are Tool_1.py ... Tool_12.py
# ============================================================
def _tool_number(tool_label: str) -> int | None:
    m = re.search(r"(\d{1,2})", (tool_label or "").strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _resolve_tool_page_file(selected_tool: str) -> str | None:
    n = _tool_number(selected_tool)
    if n is None:
        return None

    exact = f"Tool_{n}.py"
    if (PAGES_DIR / exact).exists():
        return exact

    for alt in [f"Tool {n}.py", f"Tool{n}.py", f"tool_{n}.py", f"tool{n}.py", f"tool {n}.py"]:
        if (PAGES_DIR / alt).exists():
            return alt

    for p in PAGES_DIR.glob("*.py"):
        if re.search(rf"^tool[\s_]*0*{n}\.py$", p.name, flags=re.IGNORECASE):
            return p.name

    return None


# ============================================================
# UI
# ============================================================
st.markdown("## WASH Pro")
st.markdown("Select a tool and TPM ID to continue.")
st.caption("WASH • UNICEF")

selected_tool = st.selectbox(
    "Tool",
    TOOLS,
    index=TOOLS.index(st.session_state["selected_tool"]) if st.session_state["selected_tool"] in TOOLS else 0,
    key="selected_tool",
)

with st.spinner("Loading TPM list..."):
    tpm_ids, load_error = _safe_load_tpm_ids(selected_tool)

options = [""] + tpm_ids
if st.session_state["tpm_id"] not in options:
    st.session_state["tpm_id"] = ""

selected_tpm_id = st.selectbox("TPM ID", options=options, key="tpm_id")

if load_error:
    st.error(load_error)

login_disabled = (not selected_tpm_id) or bool(load_error)

login_clicked = st.button(
    "Continue",
    type="primary",
    disabled=login_disabled,
    use_container_width=True,
)

st.caption("Tip: choose TPM ID first, then continue.")


# ============================================================
# Navigation
# ============================================================
if login_clicked:
    # Lock TPM for tool pages
    st.session_state["_tpm_id_locked"] = selected_tpm_id

    page_file = _resolve_tool_page_file(selected_tool)
    if not page_file:
        n = _tool_number(selected_tool)
        st.error(
            f"Cannot resolve target page for: {selected_tool}\n\n"
            f"Expected file: pages/Tool_{n}.py\n"
            f"Pages folder: {PAGES_DIR}"
        )
        st.stop()

    st.switch_page(f"pages/{page_file}")
