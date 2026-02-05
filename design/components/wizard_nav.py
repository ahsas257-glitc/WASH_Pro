# design/components/wizard_nav.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple
import streamlit as st
import textwrap


def _html(s: str) -> str:
    return textwrap.dedent(s).strip()


@dataclass(frozen=True)
class WizardNavStyle:
    back_label: str = "Back"
    next_label: str = "Next"
    generate_label: str = "Generate"

    # ✅ IMPORTANT: give buttons enough width so text stays on ONE line
    cols: Tuple[int, int, int] = (2, 6, 2)  # Back | spacer | Right button


def inject_wizard_nav_style() -> None:
    key = "wiz_nav__css_injected"
    if st.session_state.get(key):
        return
    st.session_state[key] = True

    st.markdown(
        _html("""
<style>
.wiz-nav-wrap{
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(255,255,255,0.14);
  background: linear-gradient(135deg, rgba(255,255,255,0.10), rgba(255,255,255,0.06));
  box-shadow: 0 14px 40px rgba(0,0,0,0.18);
  backdrop-filter: blur(14px) saturate(1.15);
  position: relative;
  overflow: hidden;
}
.wiz-nav-wrap::before{
  content:"";
  position:absolute;
  inset:-2px;
  pointer-events:none;
  background:
    radial-gradient(520px 200px at 20% 20%, rgba(90,170,255,0.22), transparent 60%),
    radial-gradient(520px 220px at 80% 30%, rgba(170,90,255,0.18), transparent 60%),
    radial-gradient(520px 240px at 50% 120%, rgba(255,140,70,0.12), transparent 60%);
  filter: blur(16px);
  opacity: .85;
}

/* Buttons */
.wiz-nav-wrap div.stButton > button{
  border: none !important;
  border-radius: 14px !important;
  padding: .72rem 1rem !important;
  font-weight: 900 !important;
  letter-spacing: .2px;
  transition: transform .15s ease, box-shadow .2s ease, filter .2s ease, opacity .2s ease;
  position: relative;
  overflow: hidden;

  /* ✅ Keep text in ONE line */
  white-space: nowrap !important;
  min-width: 140px;               /* prevents tiny narrow buttons */
  text-align: center !important;
}

.wiz-nav-wrap div.stButton > button::before{
  content:"";
  position:absolute;
  inset:-1px;
  background: linear-gradient(120deg, rgba(255,255,255,0.0), rgba(255,255,255,0.22), rgba(255,255,255,0.0));
  transform: translateX(-120%);
  transition: transform .7s ease;
  pointer-events:none;
}
.wiz-nav-wrap div.stButton > button:hover::before{
  transform: translateX(120%);
}
.wiz-nav-wrap div.stButton > button:active{
  transform: translateY(1px) scale(.99);
}

/* Back: secondary glass */
.wiz-nav-wrap div.stButton > button[kind="secondary"],
.wiz-nav-wrap div.stButton > button:not([kind]){
  background: rgba(255,255,255,0.10) !important;
  color: inherit !important;
  border: 1px solid rgba(255,255,255,0.18) !important;
  box-shadow: 0 10px 24px rgba(0,0,0,0.12);
}
.wiz-nav-wrap div.stButton > button[kind="secondary"]:hover,
.wiz-nav-wrap div.stButton > button:not([kind]):hover{
  transform: translateY(-1px);
  box-shadow: 0 14px 34px rgba(0,0,0,0.18);
  filter: brightness(1.03);
}

/* Next/Generate: primary */
.wiz-nav-wrap div.stButton > button[kind="primary"]{
  background: linear-gradient(135deg, rgba(80,170,255,0.96), rgba(120,95,255,0.96)) !important;
  color: #fff !important;
  box-shadow: 0 14px 36px rgba(70,120,255,0.30);
}
.wiz-nav-wrap div.stButton > button[kind="primary"]:hover{
  transform: translateY(-1px);
  box-shadow: 0 18px 46px rgba(70,120,255,0.38);
  filter: saturate(1.05);
}

/* Generate accent (only on last step) */
.wiz-nav-wrap div.stButton > button.wiz-generate{
  background: linear-gradient(135deg, rgba(255,120,70,0.96), rgba(170,90,255,0.96)) !important;
  box-shadow: 0 14px 38px rgba(200,90,255,0.26);
}
.wiz-nav-wrap div.stButton > button.wiz-generate:hover{
  box-shadow: 0 20px 52px rgba(200,90,255,0.34);
  filter: saturate(1.06);
}

/* Disabled */
.wiz-nav-wrap div.stButton > button:disabled{
  opacity: .55 !important;
  box-shadow: none !important;
  transform: none !important;
  cursor: not-allowed !important;
}
</style>
        """),
        unsafe_allow_html=True,
    )


def wizard_nav_ui(
    *,
    tool_key: str,
    step_idx: int,
    total_steps: int,
    is_first: bool,
    can_next: bool,
    is_last: bool,
    next_label: Optional[str] = None,
    back_label: Optional[str] = None,
    generate_label: Optional[str] = None,
    style: Optional[WizardNavStyle] = None,
) -> Tuple[bool, bool]:
    inject_wizard_nav_style()

    s = style or WizardNavStyle()
    back_text = back_label or s.back_label
    next_text = next_label or s.next_label
    gen_text = generate_label or s.generate_label

    st.markdown('<div class="wiz-nav-wrap">', unsafe_allow_html=True)

    c1, _, c3 = st.columns(list(s.cols))

    with c1:
        clicked_back = st.button(
            back_text,
            disabled=is_first,
            use_container_width=True,
            key=f"wiz__{tool_key}__back__{step_idx}",
        )

    with c3:
        right_label = gen_text if is_last else next_text
        clicked_right = st.button(
            right_label,
            disabled=(not can_next),
            type="primary",
            use_container_width=True,
            key=f"wiz__{tool_key}__right__{step_idx}",
        )

        # ✅ Make Generate visually different using CSS selector + marker
        if is_last:
            st.markdown('<div data-wiz-generate="1"></div>', unsafe_allow_html=True)

    if is_last:
        st.markdown(
            _html("""
<style>
.wiz-nav-wrap:has([data-wiz-generate="1"]) div.stButton > button[kind="primary"]{
  background: linear-gradient(135deg, rgba(255,120,70,0.96), rgba(170,90,255,0.96)) !important;
  box-shadow: 0 14px 38px rgba(200,90,255,0.26) !important;
}
.wiz-nav-wrap:has([data-wiz-generate="1"]) div.stButton > button[kind="primary"]:hover{
  box-shadow: 0 20px 52px rgba(200,90,255,0.34) !important;
  filter: saturate(1.06) !important;
}
</style>
            """),
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)
    return clicked_back, clicked_right
