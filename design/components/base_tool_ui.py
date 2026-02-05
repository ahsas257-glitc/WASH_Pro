# design/components/base_tool_ui.py
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import streamlit as st


# ============================================================
# Config (optional - kept for compatibility)
# ============================================================
@dataclass(frozen=True)
class BaseToolDesignConfig:
    project_root: str
    background_image_rel: str = "assets/images/Logo_of_PPC.png"
    background_opacity_light: float = 1.0
    background_opacity_dark: float = 1.0
    droplets: int = 14
    debug_background: bool = False


# ============================================================
# Helpers
# ============================================================
def _b64_image(path: Path | str) -> str:
    p = Path(path)
    return base64.b64encode(p.read_bytes()).decode("utf-8")


# ============================================================
# ✅ Global Liquid Glass Design (single source)
# ============================================================
def apply_global_background(
    logo_path: str = "assets/images/Logo_of_PPC.png",
    logo_opacity_light: float = 0.08,
    logo_opacity_dark: float = 0.15,
    intensity: float = 1.0,
) -> None:
    """
    Global liquid-glass background styling.
    IMPORTANT:
    - We do NOT create HTML wrappers around widgets.
    - Everything glassy is done via CSS on Streamlit native containers.
    - This prevents any raw HTML showing up.
    """
    logo_layer = ""
    p = Path(logo_path)

    if p.exists():
        try:
            b64_logo = _b64_image(p)
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
        --font-base: 18px;
        --font-label: 1rem;
        --font-h1: 2.2rem;
        --font-h2: 1.7rem;
        --font-h3: 1.35rem;

        --glass-blur: 16px;
        --glass-radius: 16px;
    }}

    body, .stApp {{
        font-size: var(--font-base);
        line-height: 1.7;
    }}

    .stMarkdown, .stText, .stCaption, .stMarkdown p {{
        font-size: var(--font-base);
        line-height: 1.85;
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
        font-size: 1.05rem;
        color: #409C9B;
        padding: 15px;
        opacity: .9;
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

    @keyframes bgLogoFloat {{
        0% {{ transform: scale(1.05) rotate(0deg); }}
        50% {{ transform: scale(1.0) rotate(0.9deg); }}
        100% {{ transform: scale(1.05) rotate(0deg); }}
    }}

    html[data-theme="dark"] {{
        --base-bg: linear-gradient(180deg, #02030a, #0b0c12);
        --c1: 60,160,255;
        --c2: 255,120,50;

        --card-bg: rgba(12,13,27,0.45);
        --card-border: rgba(255,255,255,0.12);
        --card-shadow: 0 14px 40px rgba(0,0,0,0.60);

        --text-primary: #e5e9f0;
        --muted: rgba(229,233,240,0.75);

        --btn-bg: #2e74e1;
        --btn-color: #fafafa;

        --logo-opacity: {logo_opacity_dark};
        --logo-filter: brightness(1.15) contrast(1.1);
    }}

    html[data-theme="light"] {{
        --base-bg: linear-gradient(180deg, #eef2f7, #dfe6f2);
        --c1: 40,130,255;
        --c2: 255,140,55;

        --card-bg: rgba(255,255,255,0.60);
        --card-border: rgba(200,200,210,0.35);
        --card-shadow: 0 12px 24px rgba(0,0,0,0.10);

        --text-primary: #222;
        --muted: rgba(0,0,0,0.62);

        --btn-bg: #1f78d1;
        --btn-color: #fff;

        --logo-opacity: {logo_opacity_light};
        --logo-filter: brightness(1.25) contrast(1.05);
    }}

    /* ✅ Make Streamlit surfaces GLASS (no HTML wrappers needed) */
    section[data-testid="stSidebar"],
    .main > div,
    div[data-testid="stExpander"],
    div[data-testid="stContainer"],
    div[data-testid="stVerticalBlock"] > div {{
        background: var(--card-bg) !important;
        border-radius: var(--glass-radius);
        border: 1px solid var(--card-border);
        box-shadow: var(--card-shadow);
        padding: 1.25rem;
        margin-bottom: 1.25rem;
        backdrop-filter: blur(var(--glass-blur)) saturate(1.12);
        -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(1.12);
    }}

    /* Buttons */
    button {{
        background: var(--btn-bg) !important;
        color: var(--btn-color) !important;
        border: 1px solid rgba(255,255,255,0.14) !important;
        border-radius: 12px !important;
        padding: .7rem 1.2rem !important;
        font-weight: 800 !important;
        font-size: var(--font-base);
        box-shadow: 0 14px 40px rgba(0,0,0,0.18);
    }}
    button:hover {{
        filter: brightness(1.05);
        box-shadow: 0px 10px 26px rgba(0,0,0,0.25);
    }}

    /* Input readability */
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea {{
        color: var(--text-primary) !important;
        caret-color: var(--text-primary) !important;
    }}
    div[data-baseweb="input"] input::placeholder,
    div[data-baseweb="textarea"] textarea::placeholder {{
        opacity: .65 !important;
    }}

    /* Variants (kept for compatibility; used only as small accent) */
    .lg-variant-cyan {{ outline: 1px solid rgba(60,160,255,.25); outline-offset: 6px; border-radius: 14px; }}
    .lg-variant-orange {{ outline: 1px solid rgba(255,140,55,.22); outline-offset: 6px; border-radius: 14px; }}
    .lg-variant-green {{ outline: 1px solid rgba(80,220,140,.22); outline-offset: 6px; border-radius: 14px; }}
    .lg-variant-red {{ outline: 1px solid rgba(255,80,80,.22); outline-offset: 6px; border-radius: 14px; }}

    {logo_layer}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# ============================================================
# UI helpers (NO HTML => no raw HTML shown)
# ============================================================
def topbar(title: str, subtitle: str = "", right_chip: str = "") -> None:
    c1, c2 = st.columns([7, 3], vertical_alignment="top")
    with c1:
        st.markdown(f"### {title}")
        if subtitle:
            st.caption(subtitle)

    with c2:
        if right_chip:
            # simple chip without HTML
            st.markdown(f"**{right_chip}**")


def status_card(title: str, message: str, level: str = "info") -> None:
    icon = {"info": "ℹ️", "warning": "⚠️", "error": "⛔", "success": "✅"}.get(level, "ℹ️")
    # Use Streamlit native messages (never shows raw HTML)
    if level == "error":
        st.error(f"{icon} {title}\n\n{message}")
    elif level == "warning":
        st.warning(f"{icon} {title}\n\n{message}")
    elif level == "success":
        st.success(f"{icon} {title}\n\n{message}")
    else:
        st.info(f"{icon} {title}\n\n{message}")


# ============================================================
# ✅ Card wrappers expected by step files (NO HTML wrappers!)
# ============================================================
def card_open(
    title: str = "",
    subtitle: str = "",
    variant: str = "",
    pad: int = 16,
    margin_bottom: int = 14,
) -> None:
    """
    Compatibility wrapper for step modules.
    We do NOT open HTML tags. We only render a header.
    This prevents raw HTML from appearing and keeps layout stable.
    """
    # Optional accent line / spacing (variant preserved but no HTML)
    if title:
        st.markdown(f"#### {title}")
    if subtitle:
        st.caption(subtitle)

    # small visual spacer
    st.write("")


def card_close() -> None:
    # No-op for compatibility
    return


# ============================================================
# Backward-compatible aliases
# ============================================================
def glass_open(pad: int = 16, margin_bottom: int = 14) -> None:
    card_open(pad=pad, margin_bottom=margin_bottom)


def glass_close() -> None:
    card_close()
