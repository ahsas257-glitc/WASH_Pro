from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple
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


def wizard_nav_ui(*args: Any, **kwargs: Any) -> Tuple[bool, bool]:
    """
    Modern wizard navigation UI with glassmorphism styling and full theme support.
    Returns (clicked_back, clicked_right) for wizard navigation.
    """

    # Extract parameters
    can_next = bool(kwargs.get("can_next", True))
    disable_back = bool(kwargs.get("disable_back", False))
    total_steps = kwargs.get("total_steps", 1)
    current_step = kwargs.get("current_step", 1)

    disable_next = kwargs.get("disable_next")
    if disable_next is None:
        disable_next = not can_next
    disable_next = bool(disable_next)

    back_label = str(kwargs.get("back_label", "Back"))
    next_label = str(kwargs.get("next_label", "Next"))
    generate_label = str(kwargs.get("generate_label", "Generate"))

    style = kwargs.get("style")
    if isinstance(style, WizardNavStyle):
        back_label = style.back_label or back_label
        next_label = style.next_label or next_label
        generate_label = style.generate_label or generate_label
        back_icon = style.back_icon or "◀"
        next_icon = style.next_icon or "▶"
        generate_icon = style.generate_icon or "⚡"
    else:
        back_icon = "◀"
        next_icon = "▶"
        generate_icon = "⚡"

    tool_key = str(kwargs.get("tool_key", "") or kwargs.get("key_prefix", "") or "wiz")
    step_idx = kwargs.get("step_idx", kwargs.get("step", ""))
    suffix = f"{tool_key}-{step_idx}".strip("-")

    # Inject modern CSS for wizard navigation
    st.markdown("""
    <style>
    /* Wizard Navigation CSS Variables */
    :root {
        --nav-primary-light: #667eea;
        --nav-primary-dark: #764ba2;
        --nav-secondary-light: #f1f5f9;
        --nav-secondary-dark: #334155;
        --nav-text-light: #000000;
        --nav-text-dark: #ffffff;
        --nav-border-light: rgba(0, 0, 0, 0.1);
        --nav-border-dark: rgba(255, 255, 255, 0.1);
        --nav-glass-bg-light: rgba(255, 255, 255, 0.2);
        --nav-glass-bg-dark: rgba(30, 30, 46, 0.2);
    }

    /* Modern Button Styling */
    .stButton > button {
        border-radius: 12px !important;
        border: 1px solid transparent !important;
        padding: 0.75rem 1.5rem !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
        backdrop-filter: blur(10px) !important;
        -webkit-backdrop-filter: blur(10px) !important;
        position: relative !important;
        overflow: hidden !important;
    }

    /* Primary Button (Next/Generate) */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, var(--nav-primary-light), #764ba2) !important;
        color: white !important;
        border: none !important;
        box-shadow: 0 4px 20px rgba(102, 126, 234, 0.3) !important;
    }

    .stButton > button[kind="primary"]:hover:not(:disabled) {
        transform: translateY(-2px) !important;
        box-shadow: 0 8px 30px rgba(102, 126, 234, 0.4) !important;
        background: linear-gradient(135deg, #5a6fd8, #6a4192) !important;
    }

    .stButton > button[kind="primary"]:active:not(:disabled) {
        transform: translateY(0) !important;
    }

    /* Secondary Button (Back) */
    .stButton > button:not([kind="primary"]) {
        background: var(--nav-glass-bg-light) !important;
        color: var(--nav-text-light) !important;
        border: 1px solid var(--nav-border-light) !important;
    }

    .stButton > button:not([kind="primary"]):hover:not(:disabled) {
        background: rgba(241, 245, 249, 0.8) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1) !important;
    }

    /* Dark Mode Button Adjustments */
    [data-theme="dark"] .stButton > button:not([kind="primary"]) {
        background: var(--nav-glass-bg-dark) !important;
        color: var(--nav-text-dark) !important;
        border: 1px solid var(--nav-border-dark) !important;
    }

    [data-theme="dark"] .stButton > button:not([kind="primary"]):hover:not(:disabled) {
        background: rgba(51, 65, 85, 0.8) !important;
    }

    /* Disabled State */
    .stButton > button:disabled {
        opacity: 0.5 !important;
        cursor: not-allowed !important;
        transform: none !important;
        box-shadow: none !important;
    }

    /* Progress Bar Styling */
    .wizard-progress {
        height: 6px;
        background: rgba(0, 0, 0, 0.1);
        border-radius: 3px;
        margin: 1.5rem 0;
        overflow: hidden;
    }

    .wizard-progress-fill {
        height: 100%;
        background: linear-gradient(90deg, var(--nav-primary-light), #764ba2);
        border-radius: 3px;
        transition: width 0.5s ease;
    }

    [data-theme="dark"] .wizard-progress {
        background: rgba(255, 255, 255, 0.1);
    }

    /* Step Indicator */
    .step-indicator {
        display: flex;
        justify-content: center;
        gap: 0.5rem;
        margin: 1rem 0;
    }

    .step-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: rgba(0, 0, 0, 0.2);
        transition: all 0.3s ease;
    }

    .step-dot.active {
        background: var(--nav-primary-light);
        transform: scale(1.2);
    }

    [data-theme="dark"] .step-dot {
        background: rgba(255, 255, 255, 0.2);
    }

    /* Icon Styling */
    .btn-icon {
        margin-right: 0.5rem;
        font-size: 1.1em;
        vertical-align: middle;
    }

    /* Container Styling */
    .wizard-nav-container {
        margin-top: 2rem;
        padding-top: 1.5rem;
        border-top: 1px solid var(--nav-border-light);
    }

    [data-theme="dark"] .wizard-nav-container {
        border-top-color: var(--nav-border-dark);
    }
    </style>
    """, unsafe_allow_html=True)

    # Show progress bar if total steps provided
    if total_steps > 1:
        progress = min(current_step / total_steps, 1.0)
        st.markdown(f"""
        <div class="wizard-progress">
            <div class="wizard-progress-fill" style="width: {progress * 100}%"></div>
        </div>
        """, unsafe_allow_html=True)

        # Step dots indicator
        dots_html = '<div class="step-indicator">'
        for i in range(1, total_steps + 1):
            active_class = "active" if i == current_step else ""
            dots_html += f'<div class="step-dot {active_class}"></div>'
        dots_html += '</div>'
        st.markdown(dots_html, unsafe_allow_html=True)

    # Create navigation container
    st.markdown('<div class="wizard-nav-container">', unsafe_allow_html=True)

    # Determine if this is the final step (generate instead of next)
    is_final_step = kwargs.get("is_final_step", False)
    if is_final_step:
        right_label = generate_label
        right_icon = generate_icon
    else:
        right_label = next_label
        right_icon = next_icon

    # Create columns for navigation buttons
    col1, col2 = st.columns([1, 1], gap="medium")

    with col1:
        back_button_text = f'{back_icon} {back_label}' if back_icon else back_label
        clicked_back = st.button(
            back_button_text,
            disabled=disable_back,
            use_container_width=True,
            key=f"wiz_back_{suffix}",
            help="Go to previous step"
        )

    with col2:
        right_button_text = f'{right_label} {right_icon}' if right_icon else right_label
        clicked_right = st.button(
            right_button_text,
            type="primary",
            disabled=disable_next,
            use_container_width=True,
            key=f"wiz_next_{suffix}",
            help=("Generate final output" if is_final_step else "Continue to next step")
        )

    st.markdown('</div>', unsafe_allow_html=True)

    # Add some visual feedback
    if clicked_back:
        st.toast("Going back to previous step...", icon="↩️")
    elif clicked_right and is_final_step:
        st.toast("Generating your content...", icon="⚡")
    elif clicked_right:
        st.toast("Moving to next step...", icon="↪️")

    return clicked_back, clicked_right


def create_step_header(step_number: int, title: str, description: str = "") -> None:
    """
    Create a modern step header with glassmorphism effect.
    """
    st.markdown(f"""
    <div style='
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.1), rgba(118, 75, 162, 0.1));
        backdrop-filter: blur(10px);
        border-radius: 16px;
        padding: 1.5rem;
        margin-bottom: 2rem;
        border: 1px solid rgba(102, 126, 234, 0.2);
    '>
        <div style='
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 0.5rem;
        '>
            <div style='
                background: linear-gradient(135deg, #667eea, #764ba2);
                color: white;
                width: 40px;
                height: 40px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: bold;
                font-size: 1.2rem;
            '>
                {step_number}
            </div>
            <h2 style='
                margin: 0;
                background: linear-gradient(135deg, #667eea, #764ba2);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            '>
                {title}
            </h2>
        </div>
        {f'<p style="margin: 0.5rem 0 0 0; opacity: 0.9; font-size: 1rem;">{description}</p>' if description else ''}
    </div>
    """, unsafe_allow_html=True)