from __future__ import annotations

import html
import streamlit as st
from design import apply_glassmorphism


# ----------------------------
# Helpers
# ----------------------------
def _esc(x: str) -> str:
    return html.escape(x or "")


def _inject_component_css() -> None:
    """
    Minimal component CSS.
    IMPORTANT:
      - Do NOT redefine theme variables here.
      - Use the tokens already provided by modern_glass.css
        مثل: --glass-secondary, --glass-tertiary, --border, --border-strong, --text-primary ...
    """
    st.markdown(
        """
<style id="base-tool-ui-components">
/* ============================================================
   Base Tool UI Components (minimal, token-based)
   ============================================================ */

/* Topbar */
.bt-topbar{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap: 12px;
  padding: 0.6rem 0.2rem 0.2rem 0.2rem;
}
.bt-topbar__left{
  min-width: 0;
}
.bt-topbar__title{
  margin: 0;
  font-size: 1.65rem;
  font-weight: 820;
  line-height: 1.15;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
.bt-topbar__subtitle{
  margin: 0.35rem 0 0 0;
  color: var(--text-secondary);
  opacity: 0.92;
  font-size: 0.98rem;
  line-height: 1.45;
}
.bt-topbar__right{
  flex: 0 0 auto;
  display:flex;
  align-items:center;
  justify-content:flex-end;
  padding-top: 0.10rem;
}
.bt-chip{
  display:inline-flex;
  align-items:center;
  gap: 8px;
  padding: 0.42rem 0.90rem;
  border-radius: 999px;
  background: var(--glass-tertiary);
  border: 1px solid var(--border);
  color: var(--text-primary);
  font-size: 0.90rem;
  font-weight: 700;
  box-shadow: var(--shadow-light);
  backdrop-filter: blur(var(--blur-light)) saturate(1.2);
  -webkit-backdrop-filter: blur(var(--blur-light)) saturate(1.2);
}

/* Modern divider (instead of st.markdown("---")) */
.bt-divider{
  height: 1px;
  width: 100%;
  margin: 0.85rem 0 1.05rem 0;
  background: linear-gradient(90deg, transparent, var(--border-strong), transparent);
  opacity: 0.9;
}

/* Status card accent bar */
.bt-status{
  position: relative;
  overflow: hidden;
}
.bt-status::before{
  content: "";
  position:absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 5px;
  opacity: 0.95;
}
.bt-status--info::before{    background: rgba(33,150,243,0.95); }
.bt-status--warning::before{ background: rgba(255,152,0,0.95); }
.bt-status--error::before{   background: rgba(244,67,54,0.95); }
.bt-status--success::before{ background: rgba(76,175,80,0.95); }

/* Status inner spacing */
.bt-status__body{
  padding-left: 0.35rem; /* room for the bar */
}

/* Card headings inside our cards */
.bt-card-title{
  margin: 0 0 0.65rem 0;
  font-weight: 820;
  font-size: 1.22rem;
  line-height: 1.25;
  color: var(--text-primary);
}
.bt-card-subtitle{
  margin: 0 0 1rem 0;
  color: var(--text-secondary);
  opacity: 0.92;
  font-size: 0.95rem;
  line-height: 1.45;
}
.bt-card-text{
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.65;
}

/* Small spacer after cards (optional) */
.bt-card-spacer{
  height: 0.85rem;
}

/* Ensure markdown blocks don't add huge margins */
.bt-reset-markdown .stMarkdown,
.bt-reset-markdown .stCaption{
  margin-bottom: 0.5rem !important;
}
</style>
""",
        unsafe_allow_html=True,
    )


# ----------------------------
# Public API
# ----------------------------
def apply_global_background(*args, **kwargs) -> None:
    """
    Apply global theme + component CSS.
    - Calls apply_glassmorphism() which sets tokens + html[data-theme]
    - Injects only minimal component CSS (no theme duplication)
    """
    apply_glassmorphism()
    _inject_component_css()


def topbar(*args, **kwargs) -> None:
    """
    Modern topbar (token-based).
    Usage:
      topbar("Title", subtitle="...", right_chip="...")
    """
    title = kwargs.get("title") or (args[0] if args else "")
    subtitle = kwargs.get("subtitle", "")
    right = kwargs.get("right_chip", "")

    title_h = _esc(title)
    subtitle_h = _esc(subtitle)
    right_h = _esc(right)

    st.markdown(
        f"""
<div class="bt-topbar bt-reset-markdown">
  <div class="bt-topbar__left">
    {"<h2 class='bt-topbar__title'>" + title_h + "</h2>" if title_h else ""}
    {"<p class='bt-topbar__subtitle'>" + subtitle_h + "</p>" if subtitle_h else ""}
  </div>
  <div class="bt-topbar__right">
    {"<span class='bt-chip'>" + right_h + "</span>" if right_h else ""}
  </div>
</div>
<div class="bt-divider"></div>
""",
        unsafe_allow_html=True,
    )


def status_card(title: str, message: str, level: str = "info", *_, **__) -> None:
    """
    Status card using the same glass card base.
    level: info | warning | error | success
    """
    lvl = (level or "info").strip().lower()
    if lvl not in {"info", "warning", "error", "success"}:
        lvl = "info"

    title_h = _esc(title)
    msg_h = _esc(message)

    st.markdown(
        f"""
<div class="pure-glass-card bt-status bt-status--{lvl}">
  <div class="bt-status__body">
    <h3 class="bt-card-title">{title_h}</h3>
    <p class="bt-card-text">{msg_h}</p>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def card_open(*args, **kwargs) -> None:
    """
    Open a unified glass card wrapper.
    IMPORTANT: call card_close() after content.

    Usage:
      card_open("Title", subtitle="...")
      ... streamlit widgets ...
      card_close()
    """
    title = args[0] if args else ""
    subtitle = kwargs.get("subtitle", "")

    title_h = _esc(title)
    subtitle_h = _esc(subtitle)

    # Use ONE consistent class used across app: pure-glass-card
    st.markdown('<div class="pure-glass-card bt-reset-markdown">', unsafe_allow_html=True)

    if title_h:
        st.markdown(f'<h3 class="bt-card-title">{title_h}</h3>', unsafe_allow_html=True)

    if subtitle_h:
        st.markdown(f'<p class="bt-card-subtitle">{subtitle_h}</p>', unsafe_allow_html=True)


def card_close(*args, **kwargs) -> None:
    """Close the card wrapper."""
    st.markdown("</div>", unsafe_allow_html=True)
    # consistent spacing after each card
    st.markdown('<div class="bt-card-spacer"></div>', unsafe_allow_html=True)


def create_card(title: str = "", content: str = "", **kwargs) -> None:
    """
    Create a full card with optional HTML content.
    Note: content is injected as-is (HTML). If content comes from user input, escape it first.
    """
    card_open(title, subtitle=kwargs.get("subtitle", ""))

    if content:
        # If you want safe-by-default, replace the next line with: _esc(content)
        st.markdown(content, unsafe_allow_html=True)

    card_close()


def modern_divider() -> None:
    """A themed divider."""
    st.markdown('<div class="bt-divider"></div>', unsafe_allow_html=True)
