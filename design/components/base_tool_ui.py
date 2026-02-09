from __future__ import annotations
import streamlit as st
from design import apply_glassmorphism
import streamlit.components.v1 as components

def apply_global_background(*args, **kwargs) -> None:
    """Apply global background with full theme support"""
    apply_glassmorphism()

    # Inject custom CSS for theme-aware styling
    st.markdown("""
    <style>
    /* Theme-aware color variables */
    :root {
        --background-primary: #FFFFFF;
        --text-primary: #000000;
        --card-background: rgba(255, 255, 255, 0.9);
        --border-color: rgba(0, 0, 0, 0.1);
        --shadow-color: rgba(0, 0, 0, 0.08);
    }

    [data-theme="dark"] {
        --background-primary: #0E1117;
        --text-primary: #FAFAFA;
        --card-background: rgba(30, 30, 46, 0.9);
        --border-color: rgba(255, 255, 255, 0.1);
        --shadow-color: rgba(0, 0, 0, 0.3);
    }

    /* Modern card styling */
    .modern-card {
        background: var(--card-background);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 4px 20px var(--shadow-color);
        backdrop-filter: blur(10px);
        transition: all 0.3s ease;
    }

    .modern-card:hover {
        box-shadow: 0 8px 30px var(--shadow-color);
        transform: translateY(-2px);
    }

    /* Ensure proper alignment */
    .stMarkdown, .stCaption {
        margin-bottom: 0.5rem !important;
    }

    .card-content {
        color: var(--text-primary) !important;
    }

    /* Light mode specific - ensure bright background */
    [data-theme="light"] {
        background-color: #FFFFFF !important;
    }

    [data-theme="light"] .card-content {
        color: #000000 !important;
    }

    [data-theme="light"] .modern-card {
        background: rgba(255, 255, 255, 0.95);
    }

    /* Light mode specific - make glass components visible */
    [data-theme="light"] div[data-baseweb="input"],
    [data-theme="light"] div[data-baseweb="textarea"],
    [data-theme="light"] div[data-baseweb="select"],
    [data-theme="light"] div[data-baseweb="spinner"] {
        border: 1px solid rgba(0, 0, 0, 0.15) !important;
        background: rgba(0, 0, 0, 0.03) !important;
    }
    [data-theme="light"] div[data-baseweb="input"] input,
    [data-theme="light"] div[data-baseweb="textarea"] textarea,
    [data-theme="light"] div[data-baseweb="spinner"] input {
        color: #000000 !important;
    }
    [data-theme="light"] div[data-baseweb="spinner"] button {
        background: rgba(0, 0, 0, 0.07) !important;
        color: #000000 !important;
    }
    [data-theme="light"] div[data-baseweb="spinner"] button:hover {
        background: rgba(0, 0, 0, 0.1) !important;
    }
    [data-theme="light"] div[data-baseweb="spinner"] button:active {
        background: rgba(0, 0, 0, 0.08) !important;
    }

    /* Dark mode specific */
    [data-theme="dark"] .card-content {
        color: #FAFAFA !important;
    }

    /* Status message styling */
    .status-message {
        padding: 1rem;
        border-radius: 8px;
        margin: 0.5rem 0;
        border-left: 4px solid;
    }

    .status-info {
        border-color: #2196F3;
        background: rgba(33, 150, 243, 0.1);
    }

    .status-warning {
        border-color: #FF9800;
        background: rgba(255, 152, 0, 0.1);
    }

    .status-error {
        border-color: #F44336;
        background: rgba(244, 67, 54, 0.1);
    }

    .status-success {
        border-color: #4CAF50;
        background: rgba(76, 175, 80, 0.1);
    }
    </style>
    """, unsafe_allow_html=True)

def topbar(*args, **kwargs) -> None:
    """Modern topbar with proper alignment"""
    title = kwargs.get("title") or (args[0] if args else "")
    subtitle = kwargs.get("subtitle", "")
    right = kwargs.get("right_chip", "")

    # Create container for proper alignment
    col1, col2, col3 = st.columns([3, 6, 3])

    with col1:
        if title:
            st.markdown(
                f"""
                <div class="card-content">
                <h2 style="margin: 0; font-weight: 600; font-size: 1.8rem;">{title}</h2>
                </div>
                """,
                unsafe_allow_html=True
            )

    with col2:
        if subtitle:
            st.markdown(
                f"""
                <div class="card-content">
                <p style="margin: 0.5rem 0; opacity: 0.8; font-size: 0.95rem;">{subtitle}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

    with col3:
        if right:
            st.markdown(
                f"""
                <div class="card-content" style="text-align: right;">
                <span style="background: rgba(100, 100, 255, 0.1); padding: 0.4rem 1rem; border-radius: 20px; font-size: 0.9rem; border: 1px solid rgba(100, 100, 255, 0.3);">
                {right}
                </span>
                </div>
                """,
                unsafe_allow_html=True
            )

    st.markdown("---")

def status_card(title: str, message: str, level: str = "info", *_, **__) -> None:
    """Modern status card with theme support"""
    level = (level or "info").lower()

    # Define level-specific styling
    level_styles = {
        "info": "status-info",
        "warning": "status-warning",
        "error": "status-error",
        "success": "status-success"
    }

    status_class = level_styles.get(level, "status-info")

    # Use container for proper card layout
    with st.container():
        st.markdown(
            f"""
            <div class="modern-card {status_class}">
                <div class="card-content">
                    <h3 style="margin: 0 0 1rem 0; font-weight: 600; font-size: 1.2rem;">{title}</h3>
                    <p style="margin: 0; line-height: 1.6;">{message}</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

def card_open(*args, **kwargs) -> None:
    """Open a modern, theme-aware card with proper alignment"""
    title = args[0] if args else ""
    subtitle = kwargs.get("subtitle", "")

    # Create card container
    card_container = st.container()

    with card_container:
        st.markdown('<div class="modern-card">', unsafe_allow_html=True)

        if title:
            st.markdown(
                f"""
                <div class="card-content">
                <h3 style="margin: 0 0 0.8rem 0; font-weight: 600; font-size: 1.3rem;">{title}</h3>
                </div>
                """,
                unsafe_allow_html=True
            )

        if subtitle:
            st.markdown(
                f"""
                <div class="card-content">
                <p style="margin: 0 0 1rem 0; opacity: 0.8; font-size: 0.95rem;">{subtitle}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

def card_close(*args, **kwargs) -> None:
    """Close the card container"""
    st.markdown('</div>', unsafe_allow_html=True)
    # Add spacing after card
    st.markdown('<div style="margin-bottom: 1.5rem;"></div>', unsafe_allow_html=True)

def create_card(title: str = "", content: str = "", **kwargs) -> None:
    """Create a complete modern card with title and content"""
    with st.container():
        card_open(title, **kwargs)
        if content:
            st.markdown(
                f"""
                <div class="card-content">
                <div style="padding: 1rem 0;">
                {content}
                </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        card_close()

def modern_divider() -> None:
    """Add a modern divider between sections"""
    st.markdown(
        """
        <div style="height: 1px; background: linear-gradient(90deg, transparent, var(--border-color), transparent); margin: 2rem 0;"></div>
        """,
        unsafe_allow_html=True
    )
