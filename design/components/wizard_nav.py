from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple
import html
import re

import streamlit as st


@dataclass(frozen=True)
class WizardNavStyle:
    back_label: str = "Back"
    next_label: str = "Next"
    generate_label: str = "Generate"
    use_container_width: bool = True
    back_icon: str = "◀"
    next_icon: str = "▶"
    generate_icon: str = "⚡"


def _esc(x: str) -> str:
    return html.escape(x or "")


def _safe_key(x: str) -> str:
    x = (x or "").strip()
    x = re.sub(r"[^a-zA-Z0-9_-]+", "-", x)
    x = re.sub(r"-{2,}", "-", x).strip("-")
    return x or "wiz"


def _inject_wizard_css() -> None:
    """
    Inject wizard CSS once. Fully scoped. Uses global tokens from modern_glass.css.
    Fixes:
      - harsh top line -> gradient divider
      - black band over buttons -> z-index + isolation + no bleed
      - no global .stButton overrides
    """
    if st.session_state.get("_wiz_nav_css_injected"):
        return
    st.session_state["_wiz_nav_css_injected"] = True

    st.markdown(
        """
<style id="wiz-nav-css">
/* ============================================================
   Wizard Nav (SCOPED + BLEED SAFE)
   ============================================================ */

/* Scope wrapper to ensure we never leak styles */
.wiz-scope{
  position: relative;
  isolation: isolate;          /* ✅ prevents bleed from outside stacking contexts */
  z-index: 2;
}

/* Progress */
.wiz-progress{
  height: 7px;
  background: rgba(127,127,127,0.18);
  border-radius: 999px;
  overflow: hidden;
  margin: 1.0rem 0 0.85rem 0;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-light);
  backdrop-filter: blur(var(--blur-light)) saturate(1.2);
  -webkit-backdrop-filter: blur(var(--blur-light)) saturate(1.2);
}
.wiz-progress__fill{
  height: 100%;
  width: 0%;
  background: var(--button-primary);
  border-radius: 999px;
  transition: width 0.45s ease;
}

/* Dots */
.wiz-dots{
  display:flex;
  justify-content:center;
  gap: 0.55rem;
  margin: 0.75rem 0 0.25rem 0;
}
.wiz-dot{
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: rgba(127,127,127,0.25);
  border: 1px solid var(--border);
  transition: transform 0.25s ease, opacity 0.25s ease;
  opacity: 0.85;
}
.wiz-dot.is-active{
  background: var(--text-accent);
  border-color: var(--border-strong);
  transform: scale(1.15);
  opacity: 1;
}

/* Nav container */
.wiz-nav{
  position: relative;
  z-index: 5;                 /* ✅ ensure buttons sit above any shadows */
  margin-top: 1.35rem;
  padding-top: 1.05rem;
  border-top: none !important; /* ✅ remove harsh border line */
}

/* ✅ Soft divider instead of border-top */
.wiz-nav::before{
  content: "";
  display: block;
  height: 1px;
  width: 100%;
  margin-bottom: 1.05rem;
  background: linear-gradient(90deg, transparent, var(--border-strong), transparent);
  opacity: 0.92;
}

/* Buttons: scoped to wizard area only */
.wiz-scope .wiz-nav .stButton > button{
  border-radius: 14px !important;
  font-weight: 820 !important;
  padding: 0.78rem 1.25rem !important;
  transition: transform var(--transition-fast), box-shadow var(--transition-fast), background var(--transition-fast) !important;
  backdrop-filter: blur(var(--blur-light)) saturate(1.2) !important;
  -webkit-backdrop-filter: blur(var(--blur-light)) saturate(1.2) !important;
}

/* Primary (Next/Generate) */
.wiz-scope .wiz-nav .stButton > button[kind="primary"],
.wiz-scope .wiz-nav .stButton > button[data-testid="baseButton-primary"]{
  background: var(--button-primary) !important;
  border: none !important;
  color: #fff !important;
  box-shadow: var(--shadow-light) !important;
}
.wiz-scope .wiz-nav .stButton > button[kind="primary"]:hover:not(:disabled),
.wiz-scope .wiz-nav .stButton > button[data-testid="baseButton-primary"]:hover:not(:disabled){
  background: var(--button-hover) !important;
  transform: translateY(-2px) !important;
  box-shadow: var(--shadow-medium) !important;
}
.wiz-scope .wiz-nav .stButton > button[kind="primary"]:active:not(:disabled),
.wiz-scope .wiz-nav .stButton > button[data-testid="baseButton-primary"]:active:not(:disabled){
  transform: translateY(0px) !important;
}

/* Secondary (Back) */
.wiz-scope .wiz-nav .stButton > button:not([kind="primary"]){
  background: var(--glass-tertiary) !important;
  border: 1px solid var(--border) !important;
  color: var(--text-primary) !important;
  box-shadow: var(--shadow-light) !important;
}
.wiz-scope .wiz-nav .stButton > button:not([kind="primary"]):hover:not(:disabled){
  transform: translateY(-2px) !important;
  border-color: var(--border-strong) !important;
  box-shadow: var(--shadow-medium) !important;
}

/* Disabled */
.wiz-scope .wiz-nav .stButton > button:disabled{
  opacity: 0.55 !important;
  cursor: not-allowed !important;
  transform: none !important;
  box-shadow: none !important;
}

/* ✅ Anti-bleed: BaseWeb input shadows should not draw above buttons area */
.wiz-scope div[data-baseweb="input"],
.wiz-scope div[data-baseweb="textarea"],
.wiz-scope div[data-baseweb="select"],
.wiz-scope div[data-baseweb="datepicker"],
.wiz-scope div[data-baseweb="spinner"]{
  position: relative !important;
  z-index: 1 !important;
}

/* Step header */
.wiz-step{
  margin-bottom: 1.25rem;
  overflow: hidden;          /* ✅ clip rounded edges */
}
.wiz-step__wrap{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap: 14px;
}
.wiz-step__left{
  display:flex;
  align-items:flex-start;
  gap: 12px;
  min-width: 0;
}
.wiz-step__badge{
  width: 42px;
  height: 42px;
  border-radius: 999px;
  display:flex;
  align-items:center;
  justify-content:center;
  color: #fff;
  font-weight: 900;
  background: var(--button-primary);
  box-shadow: var(--shadow-light);
  flex: 0 0 auto;
}
.wiz-step__texts{ min-width: 0; }
.wiz-step__title{
  margin: 0;
  color: var(--text-primary);
  font-weight: 860;
  font-size: 1.45rem;
  line-height: 1.2;
}
.wiz-step__desc{
  margin: 0.45rem 0 0 0;
  color: var(--text-secondary);
  font-size: 0.98rem;
  line-height: 1.5;
  opacity: 0.95;
}
</style>
""",
        unsafe_allow_html=True,
    )


def wizard_nav_ui(*args: Any, **kwargs: Any) -> Tuple[bool, bool]:
    """
    Wizard navigation UI (scoped, bleed-safe).
    Returns (clicked_back, clicked_right).
    """
    _inject_wizard_css()

    can_next = bool(kwargs.get("can_next", True))
    disable_back = bool(kwargs.get("disable_back", False))

    total_steps = int(kwargs.get("total_steps", 1) or 1)
    current_step = int(kwargs.get("current_step", 1) or 1)
    current_step = max(1, min(current_step, total_steps if total_steps > 0 else 1))

    disable_next = kwargs.get("disable_next")
    if disable_next is None:
        disable_next = not can_next
    disable_next = bool(disable_next)

    style = kwargs.get("style")
    if isinstance(style, WizardNavStyle):
        back_label = style.back_label or "Back"
        next_label = style.next_label or "Next"
        generate_label = style.generate_label or "Generate"
        back_icon = style.back_icon or "◀"
        next_icon = style.next_icon or "▶"
        generate_icon = style.generate_icon or "⚡"
        use_cw = bool(style.use_container_width)
    else:
        back_label = str(kwargs.get("back_label", "Back"))
        next_label = str(kwargs.get("next_label", "Next"))
        generate_label = str(kwargs.get("generate_label", "Generate"))
        back_icon = "◀"
        next_icon = "▶"
        generate_icon = "⚡"
        use_cw = bool(kwargs.get("use_container_width", True))

    tool_key = _safe_key(str(kwargs.get("tool_key", "") or kwargs.get("key_prefix", "") or "wiz"))
    step_idx = _safe_key(str(kwargs.get("step_idx", kwargs.get("step", "")) or current_step))
    suffix = _safe_key(f"{tool_key}-{step_idx}")

    is_final_step = bool(kwargs.get("is_final_step", False))
    right_label = generate_label if is_final_step else next_label
    right_icon = generate_icon if is_final_step else next_icon

    # Scope wrapper start (critical)
    st.markdown('<div class="wiz-scope">', unsafe_allow_html=True)

    # Progress UI
    if total_steps > 1:
        progress = min(current_step / max(total_steps, 1), 1.0)
        st.markdown(
            f"""
<div class="wiz-progress">
  <div class="wiz-progress__fill" style="width:{progress * 100:.2f}%"></div>
</div>
""",
            unsafe_allow_html=True,
        )

        dots = ['<div class="wiz-dots">']
        for i in range(1, total_steps + 1):
            cls = "wiz-dot is-active" if i == current_step else "wiz-dot"
            dots.append(f'<div class="{cls}"></div>')
        dots.append("</div>")
        st.markdown("".join(dots), unsafe_allow_html=True)

    # Buttons container
    st.markdown('<div class="wiz-nav">', unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1], gap="medium")

    with col1:
        back_text = f"{back_icon} {back_label}".strip()
        clicked_back = st.button(
            back_text,
            disabled=disable_back,
            use_container_width=use_cw,
            key=f"wiz_back_{suffix}",
            help="Go to previous step",
        )

    with col2:
        right_text = f"{right_label} {right_icon}".strip()
        clicked_right = st.button(
            right_text,
            type="primary",
            disabled=disable_next,
            use_container_width=use_cw,
            key=f"wiz_next_{suffix}",
            help=("Generate final output" if is_final_step else "Continue to next step"),
        )

    st.markdown("</div>", unsafe_allow_html=True)  # .wiz-nav
    st.markdown("</div>", unsafe_allow_html=True)  # .wiz-scope

    # Toast feedback
    if clicked_back:
        st.toast("Going back…", icon="↩️")
    elif clicked_right and is_final_step:
        st.toast("Generating…", icon="⚡")
    elif clicked_right:
        st.toast("Next step…", icon="↪️")

    return clicked_back, clicked_right


def create_step_header(step_number: int, title: str, description: str = "") -> None:
    """
    Step header using the same glass card system (pure-glass-card).
    """
    _inject_wizard_css()

    step_h = _esc(str(step_number))
    title_h = _esc(title)
    desc_h = _esc(description)

    st.markdown(
        f"""
<div class="wiz-scope">
  <div class="pure-glass-card wiz-step">
    <div class="wiz-step__wrap">
      <div class="wiz-step__left">
        <div class="wiz-step__badge">{step_h}</div>
        <div class="wiz-step__texts">
          <h2 class="wiz-step__title">{title_h}</h2>
          {f"<p class='wiz-step__desc'>{desc_h}</p>" if desc_h else ""}
        </div>
      </div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
