from __future__ import annotations

from pathlib import Path
import streamlit as st
import hashlib


def _read_text(path: str | Path) -> str:
    """Read CSS file with caching for performance"""
    return Path(path).read_text(encoding="utf-8")


def apply_glassmorphism(*, css_path: str | Path = "design/css/modern_glass.css") -> None:
    """
    PURE glassmorphism theme with full UI coverage:
      - Inputs (including password eye)
      - Number input spinner (+/-) perfectly styled
      - Remove grey panels behind containers/expanders
      - Sidebar typography + button alignment
      - Reduce top padding (move content upward)
    """

    css_content = _read_text(css_path)
    css_hash = hashlib.md5(css_content.encode()).hexdigest()[:8]

    st.markdown(
        f"""
<style id="glassmorphism-theme-{css_hash}">
/* ============================================================
   BASE THEME (from design/css/modern_glass.css)
   ============================================================ */
{css_content}

/* ============================================================
   GLOBAL LAYOUT FIX: reduce top padding (move up)
   ============================================================ */
.main .block-container {{
  padding-top: 0.45rem !important;
  padding-bottom: 1.0rem !important;
  max-width: 100% !important;
}}
div[data-testid="stAppViewContainer"] > .main {{
  padding-top: 0rem !important;
}}

/* ============================================================
   REMOVE STREAMLIT GREY PANELS (containers/expanders/wrappers)
   ============================================================ */
div[data-testid="stContainer"],
div[data-testid="stExpander"],
div[data-testid="stVerticalBlockBorderWrapper"],
div[data-testid="stHorizontalBlock"] {{
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}}
div[data-testid="stContainer"] > div,
div[data-testid="stVerticalBlockBorderWrapper"] > div {{
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}}
details, details > summary {{
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}}

/* ============================================================
   PURE GLASS CARDS (outer only)
   ============================================================ */
.pure-glass-card {{
  position: relative !important;
  background: rgba(255, 255, 255, 0.08) !important;
  backdrop-filter: blur(30px) saturate(200%) !important;
  -webkit-backdrop-filter: blur(30px) saturate(200%) !important;
  border-radius: 24px !important;
  border: 1px solid rgba(255, 255, 255, 0.20) !important;
  padding: 2rem !important;
  margin: 1.2rem 0 !important;
  box-shadow:
    0 20px 60px rgba(0, 0, 0, 0.15),
    inset 0 1px 0 rgba(255, 255, 255, 0.22) !important;
  transition: all 0.28s cubic-bezier(0.4, 0, 0.2, 1) !important;
  isolation: isolate !important;
  overflow: visible !important;
  z-index: 1 !important;
}}
.pure-glass-card:hover {{
  transform: translateY(-3px) !important;
  border-color: rgba(88, 153, 255, 0.28) !important;
}}

/* wrappers inside cards should not create grey layers */
.pure-glass-card .element-container,
.pure-glass-card .stMarkdown,
.pure-glass-card .stDataFrame,
.pure-glass-card .stMetric {{
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}}

/* ============================================================
   UNIVERSAL "GLASS FIELD" STYLE (inputs/selects/spinner)
   ============================================================ */
:root {{
  --glass-bg: rgba(255,255,255,0.06);
  --glass-bg-focus: rgba(255,255,255,0.09);
  --glass-border: rgba(255,255,255,0.14);
  --glass-border-focus: rgba(88,153,255,0.55);
  --glass-shadow: 0 10px 28px rgba(0,0,0,0.22);
  --glass-shadow-focus: 0 0 0 3px rgba(88,153,255,0.18), 0 14px 34px rgba(0,0,0,0.25);
  --glass-radius: 18px;
}}

/* ============================================================
   PERFECT INPUTS (GLOBAL) ✅
   ============================================================ */
div[data-baseweb="input"],
div[data-baseweb="textarea"],
div[data-baseweb="select"],
div[data-baseweb="datepicker"] {{
  border-radius: var(--glass-radius) !important;
  overflow: hidden !important;
  background: var(--glass-bg) !important;
  border: 1px solid var(--glass-border) !important;
  box-shadow: var(--glass-shadow) !important;
  backdrop-filter: blur(14px) saturate(150%) !important;
}}

div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div,
div[data-baseweb="select"] > div {{
  border-radius: var(--glass-radius) !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}}

div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea {{
  background: transparent !important;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  color: rgba(255,255,255,0.92) !important;
  font-weight: 500 !important;
}}

div[data-baseweb="input"]:focus-within,
div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="select"]:focus-within {{
  border-color: var(--glass-border-focus) !important;
  box-shadow: var(--glass-shadow-focus) !important;
  background: var(--glass-bg-focus) !important;
}}

/* password eye / enhancers */
div[data-baseweb="input"] [data-baseweb="end-enhancer"],
div[data-baseweb="input"] [data-baseweb="start-enhancer"] {{
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}}
div[data-baseweb="input"] * {{
  box-shadow: none !important;
}}

/* ============================================================
   ✅ NUMBER INPUT SPINNER (+ / -) PERFECT STYLING
   This is exactly what you circled.
   ============================================================ */

/* spinner outer wrapper gets the same glass look */
div[data-baseweb="spinner"] {{
  border-radius: var(--glass-radius) !important;
  overflow: hidden !important;
  background: var(--glass-bg) !important;
  border: 1px solid var(--glass-border) !important;
  box-shadow: var(--glass-shadow) !important;
  backdrop-filter: blur(14px) saturate(150%) !important;
}}

/* spinner internal layout (keep transparent) */
div[data-baseweb="spinner"] > div {{
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}}

/* the input inside spinner */
div[data-baseweb="spinner"] input {{
  background: transparent !important;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  color: rgba(255,255,255,0.92) !important;
  font-weight: 600 !important;
}}

/* +/- buttons inside spinner */
div[data-baseweb="spinner"] button {{
  background: rgba(255,255,255,0.07) !important;
  border: none !important;
  box-shadow: none !important;
  color: rgba(255,255,255,0.90) !important;
  border-radius: 14px !important;
  margin: 6px !important;           /* ✅ فاصله مثل کارت */
  min-width: 44px !important;
  min-height: 38px !important;
  transition: all 0.18s ease !important;
}}

/* hover/focus on +/- */
div[data-baseweb="spinner"] button:hover {{
  background: rgba(255,255,255,0.12) !important;
  transform: translateY(-1px) !important;
}}
div[data-baseweb="spinner"] button:active {{
  transform: translateY(0px) !important;
  background: rgba(255,255,255,0.10) !important;
}}

/* remove ugly separator/lines if any */
div[data-baseweb="spinner"] [role="separator"],
div[data-baseweb="spinner"] hr {{
  display: none !important;
}}

/* focus-within for spinner container */
div[data-baseweb="spinner"]:focus-within {{
  border-color: var(--glass-border-focus) !important;
  box-shadow: var(--glass-shadow-focus) !important;
  background: var(--glass-bg-focus) !important;
}}

/* ============================================================
   BUTTONS (global + inside cards)
   ============================================================ */
.stButton > button {{
  border-radius: 12px !important;
  font-weight: 700 !important;
  white-space: nowrap !important;
}}

.pure-glass-card .stButton > button {{
  background: linear-gradient(135deg, rgba(88, 153, 255, 0.90), rgba(125, 100, 255, 0.90)) !important;
  border: none !important;
  color: #fff !important;
  padding: 0.70rem 1.4rem !important;
  box-shadow: 0 6px 22px rgba(88, 153, 255, 0.28) !important;
}}
.pure-glass-card .stButton > button:hover {{
  transform: translateY(-1px) !important;
  box-shadow: 0 10px 30px rgba(88, 153, 255, 0.38) !important;
}}

/* ============================================================
   ALERTS (avoid heavy blocks)
   ============================================================ */
div[data-testid="stAlert"] {{
  background: rgba(255,255,255,0.06) !important;
  border: 1px solid rgba(255,255,255,0.10) !important;
  box-shadow: none !important;
}}

/* ============================================================
   SIDEBAR TYPOGRAPHY + SPACING
   ============================================================ */
section[data-testid="stSidebar"] {{
  backdrop-filter: blur(18px) saturate(140%) !important;
}}
section[data-testid="stSidebar"] * {{
  font-size: 12.5px !important;
  line-height: 1.25 !important;
}}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {{
  font-size: 14px !important;
  margin: 0.35rem 0 0.55rem 0 !important;
  font-weight: 750 !important;
}}
section[data-testid="stSidebar"] label {{
  font-size: 12px !important;
  opacity: 0.85 !important;
}}
section[data-testid="stSidebar"] div[data-baseweb="input"],
section[data-testid="stSidebar"] div[data-baseweb="textarea"],
section[data-testid="stSidebar"] div[data-baseweb="select"],
section[data-testid="stSidebar"] div[data-baseweb="spinner"] {{
  margin: 0.30rem 0 !important;
}}
section[data-testid="stSidebar"] .stButton > button {{
  width: 100% !important;
  min-height: 2.35rem !important;
  border-radius: 12px !important;
  padding: 0.45rem 0.90rem !important;
  font-weight: 800 !important;
}}
section[data-testid="stSidebar"] div[data-testid="column"] {{
  padding-top: 0 !important;
  padding-bottom: 0 !important;
}}

/* ============================================================
   LIGHT/DARK ADAPTATIONS
   ============================================================ */
[data-theme="light"] .pure-glass-card {{
  background: rgba(255, 255, 255, 0.12) !important;
  border-color: rgba(0, 0, 0, 0.08) !important;
}}
[data-theme="dark"] .pure-glass-card {{
  background: rgba(30, 30, 46, 0.10) !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )

    # Meta tags
    st.markdown(
        """
<meta name="theme-color" content="#0A0F1A">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
""",
        unsafe_allow_html=True,
    )


def apply_minimal_theme() -> None:
    minimal_css = """
:root {
  --radius-md: 12px;
  --radius-sm: 8px;
  --shadow-light: 0 2px 12px rgba(0, 0, 0, 0.08);
}
.stApp { background: #f8fafc !important; font-family: 'Inter', -apple-system, sans-serif !important; }
html[data-theme="dark"] .stApp { background: #0f172a !important; }
.pure-glass-card {
  background: rgba(255, 255, 255, 0.9) !important;
  border: 1px solid rgba(0, 0, 0, 0.08) !important;
  border-radius: var(--radius-md) !important;
  box-shadow: var(--shadow-light) !important;
  backdrop-filter: none !important;
}
html[data-theme="dark"] .pure-glass-card {
  background: rgba(30, 41, 59, 0.9) !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
}
"""
    st.markdown(f"<style>{minimal_css}</style>", unsafe_allow_html=True)


def get_theme_preference() -> str:
    return st.session_state.get("theme_preference", "system")


def set_theme_preference(theme: str) -> None:
    valid_themes = ["light", "dark", "system"]
    if theme not in valid_themes:
        raise ValueError(f"Theme must be one of {valid_themes}")
    st.session_state.theme_preference = theme
    st.rerun()


def theme_selector_widget() -> None:
    with st.sidebar:
        st.markdown("### 🎨 Theme")

        current_theme = get_theme_preference()
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("☀️", use_container_width=True, help="Light Theme", disabled=current_theme == "light"):
                set_theme_preference("light")

        with col2:
            if st.button("🌙", use_container_width=True, help="Dark Theme", disabled=current_theme == "dark"):
                set_theme_preference("dark")

        with col3:
            if st.button("⚙️", use_container_width=True, help="System Default", disabled=current_theme == "system"):
                set_theme_preference("system")
