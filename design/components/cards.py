# design/components/cards.py
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional, Callable, Any
import streamlit as st


@contextmanager
def glass_card(*, class_name: str = "pure-glass-card", key: Optional[str] = None) -> Iterator[None]:
    """
    PURE glass card with NO CSS injection.
    All styling is handled by apply_glassmorphism().

    Usage:
        with glass_card():
            st.write("Content on pure glass")
    """
    # NO CSS injection here - all CSS is centralized
    st.markdown(f'<div class="{class_name}">', unsafe_allow_html=True)
    try:
        yield
    finally:
        st.markdown("</div>", unsafe_allow_html=True)


@contextmanager
def pure_glass_panel(title: str = "", subtitle: str = "", variant: str = "default") -> Iterator[None]:
    """
    Pure glass panel with title.

    Variants:
    - default: Standard pure glass
    - transparent: Ultra-clean
    - frosted: Strong frost effect
    """

    variant_class = {
        "default": "pure-glass-card",
        "transparent": "pure-glass-card-transparent",
        "frosted": "pure-glass-card-frosted"
    }.get(variant, "pure-glass-card")

    with glass_card(class_name=variant_class):
        if title:
            st.markdown(
                f"""
                <div style="margin-bottom: 1rem;">
                    <h2 style="
                        margin: 0;
                        font-size: 1.8rem;
                        font-weight: 700;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        -webkit-background-clip: text;
                        -webkit-text-fill-color: transparent;
                        background-clip: text;
                        line-height: 1.3;
                    ">{title}</h2>
                </div>
                """,
                unsafe_allow_html=True
            )

        if subtitle:
            st.markdown(
                f"""
                <div style="
                    margin-bottom: 1.5rem;
                    opacity: 0.9;
                    font-size: 1rem;
                    line-height: 1.6;
                ">
                    {subtitle}
                </div>
                """,
                unsafe_allow_html=True
            )

        yield


def glass_panel(content: Any = None, title: str = "", **kwargs) -> None:
    """
    Simple glass panel.

    Usage:
        glass_panel(st.metric("Value", 100), title="Metric")
    """
    with pure_glass_panel(title=title):
        if content:
            if callable(content):
                content()
            else:
                st.write(content)


def glass_grid(items: list, cols: int = 3, variant: str = "default") -> None:
    """
    Grid of glass cards.

    Usage:
        glass_grid([
            ("Card 1", lambda: st.write("Content 1")),
            ("Card 2", lambda: st.metric("Value", 100)),
        ])
    """
    columns = st.columns(cols)

    for idx, (title, content) in enumerate(items):
        with columns[idx % cols]:
            with pure_glass_panel(title=title if isinstance(title, str) else "", variant=variant):
                if content:
                    if callable(content):
                        content()
                    else:
                        st.write(content)


# Backward compatibility
@contextmanager
def elegant_card(*, title: str = "", subtitle: str = "", variant: str = "default") -> Iterator[None]:
    """Alias for pure_glass_panel."""
    with pure_glass_panel(title=title, subtitle=subtitle, variant=variant):
        yield