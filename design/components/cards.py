# design/components/cards.py
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional, Any, Callable
import html
import streamlit as st


def _esc(text: str) -> str:
    return html.escape(text or "")


def _variant_class(variant: str) -> str:
    """
    Map variants to CSS classes (theme CSS controls the visuals).
    """
    v = (variant or "default").strip().lower()
    return {
        "default": "pure-glass-card",
        "transparent": "pure-glass-card transparent",
        "frosted": "pure-glass-card frosted",
        "tight": "pure-glass-card tight",
        "soft": "pure-glass-card soft",
    }.get(v, "pure-glass-card")


@contextmanager
def glass_card(
    *,
    class_name: str = "pure-glass-card",
    key: Optional[str] = None,
    title: str = "",
    subtitle: str = "",
    header_right: str = "",
    variant: str = "default",
    divider: bool = False,
) -> Iterator[None]:
    """
    Unified glass card with consistent internal structure.
    - No CSS injection here (centralized in apply_glassmorphism)
    - Strong edge handling: rounded corners + overflow clipping + stable padding
    - Optional header (title/subtitle/right chip) + divider

    Usage:
        with glass_card(title="A", subtitle="B"):
            st.write("...")
    """
    # Compose classes: base + user + variant
    base = _variant_class(variant)
    extra = (class_name or "").strip()
    kattr = f' data-key="{_esc(key)}"' if key else ""

    title_h = _esc(title)
    subtitle_h = _esc(subtitle)
    right_h = _esc(header_right)

    # Card open: stable wrapper + internal structure
    st.markdown(
        f"""
<div class="gc-card {base} {extra}"{kattr}>
  <div class="gc-inner">
""",
        unsafe_allow_html=True,
    )

    # Header (optional)
    if title_h or subtitle_h or right_h:
        st.markdown(
            f"""
    <div class="gc-header">
      <div class="gc-header-left">
        {"<h3 class='gc-title'>" + title_h + "</h3>" if title_h else ""}
        {"<p class='gc-subtitle'>" + subtitle_h + "</p>" if subtitle_h else ""}
      </div>
      {"<div class='gc-header-right'><span class='gc-chip'>" + right_h + "</span></div>" if right_h else ""}
    </div>
""",
            unsafe_allow_html=True,
        )

        if divider:
            st.markdown('<div class="gc-divider"></div>', unsafe_allow_html=True)

    # Body open
    st.markdown('<div class="gc-body">', unsafe_allow_html=True)

    try:
        yield
    finally:
        # Body close + card close
        st.markdown(
            """
</div> <!-- gc-body -->
</div> <!-- gc-inner -->
</div> <!-- gc-card -->
""",
            unsafe_allow_html=True,
        )


@contextmanager
def pure_glass_panel(
    title: str = "",
    subtitle: str = "",
    variant: str = "default",
    key: Optional[str] = None,
    header_right: str = "",
    divider: bool = False,
) -> Iterator[None]:
    """
    Pure glass panel with a consistent header.
    Variants: default | transparent | frosted | tight | soft
    """
    with glass_card(
        class_name="",
        key=key,
        title=title,
        subtitle=subtitle,
        header_right=header_right,
        variant=variant,
        divider=divider,
    ):
        yield


def glass_panel(content: Any = None, title: str = "", subtitle: str = "", **kwargs) -> None:
    """
    Simple helper to render one panel.

    Usage:
        glass_panel(lambda: st.metric("Value", 100), title="Metric")
    """
    with pure_glass_panel(title=title, subtitle=subtitle, **kwargs):
        if content is None:
            return
        if callable(content):
            content()
        else:
            st.write(content)


def glass_grid(items: list, cols: int = 3, variant: str = "default", gap: str = "default") -> None:
    """
    Grid of glass panels. Forces consistent height behavior by aligning columns.
    items: list of tuples (title, content, optional_subtitle)

    Example:
        glass_grid([
            ("Card 1", lambda: st.write("Content 1")),
            ("Card 2", lambda: st.metric("Value", 100), "subtitle"),
        ], cols=3)
    """
    if cols < 1:
        cols = 1

    columns = st.columns(cols)

    for idx, item in enumerate(items):
        # Support (title, content) or (title, content, subtitle)
        if len(item) == 2:
            title, content = item
            subtitle = ""
        else:
            title, content, subtitle = item[0], item[1], item[2] if len(item) > 2 else ""

        with columns[idx % cols]:
            with pure_glass_panel(
                title=title if isinstance(title, str) else "",
                subtitle=subtitle if isinstance(subtitle, str) else "",
                variant=variant,
                divider=False,
            ):
                if content is None:
                    continue
                if callable(content):
                    content()
                else:
                    st.write(content)


# Backward compatibility
@contextmanager
def elegant_card(*, title: str = "", subtitle: str = "", variant: str = "default", **kwargs) -> Iterator[None]:
    """Alias for pure_glass_panel with the new structure."""
    with pure_glass_panel(title=title, subtitle=subtitle, variant=variant, **kwargs):
        yield
