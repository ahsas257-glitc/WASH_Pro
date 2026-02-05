# src/ui/wizard.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence, Tuple

import streamlit as st
from design.components.wizard_nav import wizard_nav_ui, WizardNavStyle


def _safe_slug(s: str) -> str:
    s = (s or "").strip().lower()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("_")
    s2 = "".join(out).strip("_")
    while "__" in s2:
        s2 = s2.replace("__", "_")
    return s2 or "tool6"


@dataclass(frozen=True)
class WizardConfig:
    tool_name: str
    steps: Sequence[str]
    key_prefix: Optional[str] = None
    show_counter: bool = True


class Wizard:
    def __init__(self, config: WizardConfig):
        self.config = config
        self.steps = list(config.steps or [])
        if not self.steps:
            raise ValueError("Wizard steps cannot be empty.")

        slug = _safe_slug(config.key_prefix or config.tool_name)
        self._tool_key = slug
        self._k_step = f"wiz__{slug}__step_idx"
        self._ensure_state()

    def _ensure_state(self) -> None:
        if self._k_step not in st.session_state:
            st.session_state[self._k_step] = 0

    @property
    def step_idx(self) -> int:
        return int(st.session_state.get(self._k_step, 0))

    @property
    def step_title(self) -> str:
        return self.steps[self.step_idx]

    def set_step(self, idx: int) -> None:
        idx = max(0, min(int(idx), len(self.steps) - 1))
        st.session_state[self._k_step] = idx

    def next(self) -> None:
        if self.step_idx < len(self.steps) - 1:
            st.session_state[self._k_step] = self.step_idx + 1

    def back(self) -> None:
        if self.step_idx > 0:
            st.session_state[self._k_step] = self.step_idx - 1

    def reset(self) -> None:
        st.session_state[self._k_step] = 0

    def is_first_step(self) -> bool:
        return self.step_idx == 0

    def is_last_step(self) -> bool:
        return self.step_idx == len(self.steps) - 1

    def header(self, divider: bool = True) -> None:
        if divider:
            st.markdown("---")

        left, right = st.columns([7, 3])
        with left:
            st.subheader(self.step_title)
        with right:
            if self.config.show_counter:
                st.caption(f"Step {self.step_idx + 1} / {len(self.steps)}")

    def nav(
        self,
        *,
        can_next: bool,
        next_label: str = "Next",
        back_label: str = "Back",
        generate_label: str = "Generate",
        style: Optional[WizardNavStyle] = None,
        on_back: Optional[Callable[[], None]] = None,
        on_next: Optional[Callable[[], None]] = None,
        on_generate: Optional[Callable[[], None]] = None,
        auto_rerun: bool = True,
    ) -> Tuple[bool, bool]:
        """Render Back/Next (or Generate) buttons and handle navigation.

        Streamlit runs top-to-bottom. Many apps read `step_idx` early, then render buttons later.
        If we only update `st.session_state` on click, the current run may still render the old step
        (it feels like it needs two clicks). `st.rerun()` after changing the step fixes that.
        """
        is_last = self.is_last_step()

        clicked_back, clicked_right = wizard_nav_ui(
            tool_key=self._tool_key,
            step_idx=self.step_idx,
            total_steps=len(self.steps),
            is_first=self.is_first_step(),
            is_last=is_last,
            can_next=can_next,
            next_label=next_label,
            back_label=back_label,
            generate_label=generate_label,
            style=style,
        )

        navigated = False

        # Back
        if clicked_back:
            if on_back:
                on_back()
            else:
                self.back()
            navigated = True

        # Next / Generate
        if clicked_right:
            if is_last:
                # Generate معمولاً در همین run خروجی را رندر می‌کند،
                # پس rerun اجباری نمی‌زنیم مگر اینکه خود callback لازم داشته باشد.
                if on_generate:
                    on_generate()
            else:
                if on_next:
                    on_next()
                else:
                    self.next()
                navigated = True

        # Force immediate page switch (fix "needs two clicks")
        if auto_rerun and navigated:
            st.rerun()

        return clicked_back, clicked_right
