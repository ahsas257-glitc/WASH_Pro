from __future__ import annotations

from pathlib import Path
import hashlib
import streamlit as st


@st.cache_data(show_spinner=False)
def _read_text(path: str | Path) -> str:
    """Read text file with caching for performance."""
    return Path(path).read_text(encoding="utf-8")


def _inject_theme_runtime(*, theme_preference: str) -> None:
    """
    Apply theme preference by setting html[data-theme] to:
      - "light"
      - "dark"
      - system-resolved ("light"/"dark")
    Also removes duplicate style tags if present.
    """
    # IMPORTANT: Keep this JS small and robust.
    st.markdown(
        f"""
<script>
(function() {{
  const pref = {theme_preference!r}; // "light" | "dark" | "system"

  function systemTheme() {{
    return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)
      ? 'dark'
      : 'light';
  }}

  function applyTheme() {{
    const t = (pref === 'system') ? systemTheme() : pref;
    document.documentElement.setAttribute('data-theme', t);
    document.body.classList.remove('light','dark');
    document.body.classList.add(t);
  }}

  // Remove duplicates of our style tags (if reruns injected multiple times)
  function dedupeStyles() {{
    const ids = ['glassmorphism-base', 'glassmorphism-overrides'];
    ids.forEach((id) => {{
      const nodes = document.querySelectorAll('#' + id);
      if (nodes.length > 1) {{
        // keep last
        for (let i = 0; i < nodes.length - 1; i++) nodes[i].remove();
      }}
    }});
  }}

  applyTheme();
  dedupeStyles();

  // If system theme changes and user is on "system", update dynamically.
  if (pref === 'system' && window.matchMedia) {{
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    try {{
      mq.addEventListener('change', applyTheme);
    }} catch (e) {{
      // Safari fallback
      mq.addListener(applyTheme);
    }}
  }}
}})();
</script>
""",
        unsafe_allow_html=True,
    )


def apply_glassmorphism(*, css_path: str | Path = "design/css/modern_glass.css") -> None:
    """
    Apply glassmorphism theme with:
      - Base CSS loaded from file
      - Minimal, theme-aware overrides (no conflicts)
      - Real theme switching via html[data-theme]
      - DOM dedupe for reruns
    """

    css_content = _read_text(css_path)
    css_hash = hashlib.md5(css_content.encode("utf-8")).hexdigest()[:10]

    # 1) Base CSS from file (stable id)
    st.markdown(
        f"""
<style id="glassmorphism-base">
/* base-css-hash: {css_hash} */
{css_content}
</style>
""",
        unsafe_allow_html=True,
    )

    # 2) Overrides: keep small + theme-aware, avoid hard-coded white text
    st.markdown(
        """
<style id="glassmorphism-overrides">
/* ============================================================
   Overrides (minimal + robust)
   ============================================================ */

/* Reduce top spacing */
.main .block-container{
  padding-top: 0.55rem !important;
  padding-bottom: 1.0rem !important;
  max-width: 100% !important;
}
div[data-testid="stAppViewContainer"] > .main{
  padding-top: 0rem !important;
}

/* Consistent vertical rhythm */
div[data-testid="stVerticalBlock"]{
  gap: 0.70rem !important;
}

/* Columns: stretch children -> cards align nicely */
div[data-testid="stHorizontalBlock"]{ align-items: stretch !important; }
div[data-testid="column"]{
  display: flex !important;
  flex-direction: column !important;
  align-self: stretch !important;
}
div[data-testid="column"] > div{ width: 100% !important; }

/* Remove Streamlit default “grey panels” behind wrappers */
div[data-testid="stContainer"],
div[data-testid="stVerticalBlockBorderWrapper"],
div[data-testid="stHorizontalBlock"]{
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
div[data-testid="stContainer"] > div,
div[data-testid="stVerticalBlockBorderWrapper"] > div{
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}

/* Expander -> look like a card (instead of transparent details) */
div[data-testid="stExpander"]{
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}
div[data-testid="stExpander"] > details{
  background: var(--glass-secondary) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-md) !important;
  box-shadow: var(--shadow-light) !important;
  overflow: hidden !important;
}
div[data-testid="stExpander"] > details > summary{
  padding: 0.85rem 1rem !important;
  color: var(--text-primary) !important;
}
div[data-testid="stExpander"] > details[open]{
  box-shadow: var(--shadow-medium) !important;
}

/* PURE glass card: use theme tokens (avoid fixed rgba that breaks light) */
.pure-glass-card{
  position: relative !important;
  background: var(--glass-secondary) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-lg) !important;
  box-shadow: var(--shadow-medium) !important;
  backdrop-filter: blur(var(--blur-medium)) saturate(1.25) !important;
  -webkit-backdrop-filter: blur(var(--blur-medium)) saturate(1.25) !important;
  padding: 1.6rem !important;
  margin: 1.0rem 0 !important;
  transition: all var(--transition-medium) !important;
  isolation: isolate !important;
  z-index: 1 !important;
}
.pure-glass-card:hover{
  transform: translateY(-2px) !important;
  border-color: var(--border-strong) !important;
  box-shadow: var(--shadow-heavy), var(--shadow-glow) !important;
}

/* Inside cards: prevent nested wrappers from reintroducing backgrounds */
.pure-glass-card .element-container,
.pure-glass-card .stMarkdown,
.pure-glass-card .stDataFrame,
.pure-glass-card .stMetric{
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
}

/* Inputs: do NOT hardcode white text (use theme tokens) */
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea,
div[data-baseweb="select"] span{
  color: var(--text-primary) !important;
}

/* Placeholder */
div[data-baseweb="input"] input::placeholder,
div[data-baseweb="textarea"] textarea::placeholder{
  color: var(--text-tertiary) !important;
  opacity: 0.85 !important;
}

/* Spinner buttons: remove margins that split the box */
div[data-baseweb="spinner"] button{
  margin: 0 !important;
}

/* Alerts: lighter */
div[data-testid="stAlert"]{
  background: var(--glass-tertiary) !important;
  border: 1px solid var(--border) !important;
  box-shadow: none !important;
}

/* Sidebar: keep it consistent with base tokens (no hard overrides) */
section[data-testid="stSidebar"] .stButton > button{
  width: 100% !important;
  min-height: 2.35rem !important;
  border-radius: 12px !important;
  padding: 0.45rem 0.90rem !important;
  font-weight: 800 !important;
}
</style>
""",
        unsafe_allow_html=True,
    )

    # 3) Meta tags (safe)
    st.markdown(
        """
<meta name="theme-color" content="#0A0F1A">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
""",
        unsafe_allow_html=True,
    )

    # 4) Apply theme preference to html[data-theme] (REAL switching)
    theme_preference = get_theme_preference()
    _inject_theme_runtime(theme_preference=theme_preference)


def apply_minimal_theme() -> None:
    """
    Minimal theme (fallback / debug).
    """
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
    # "system" is default
    return st.session_state.get("theme_preference", "system")


def set_theme_preference(theme: str) -> None:
    valid = {"light", "dark", "system"}
    if theme not in valid:
        raise ValueError(f"Theme must be one of {sorted(valid)}")
    st.session_state.theme_preference = theme
    st.rerun()


def theme_selector_widget() -> None:
    with st.sidebar:
        st.markdown("### 🎨 Theme")

        current = get_theme_preference()
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("☀️", use_container_width=True, help="Light Theme", disabled=current == "light"):
                set_theme_preference("light")

        with col2:
            if st.button("🌙", use_container_width=True, help="Dark Theme", disabled=current == "dark"):
                set_theme_preference("dark")

        with col3:
            if st.button("⚙️", use_container_width=True, help="System Default", disabled=current == "system"):
                set_theme_preference("system")
