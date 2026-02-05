# src/Tools/steps/step_5_work_progress.py
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List

import streamlit as st

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card


# =============================================================================
# Session keys (Tool6 naming)
# =============================================================================
SS_OBS = "tool6_obs_components"          # Step 3 output
SS_WORK = "tool6_work_progress_rows"     # Step 5 output rows
SS_AUTO_PROGRESS = "tool6_work_auto_progress"
SS_TITLES_HASH = "tool6_work_titles_hash"  # performance: detect titles changes


# =============================================================================
# UI config
# =============================================================================
class UIConfig:
    SHOW_ROW_NUMBERS = True
    DEFAULT_EMPTY_ROWS = 3

    VALUE_MIN = 0.0
    VALUE_STEP = 1.0
    VALUE_FORMAT = "%.0f"  # change to "%.2f" if decimals needed

    PROGRESS_MIN = 0
    PROGRESS_MAX = 100
    PROGRESS_STEP = 1
    STORE_WITH_PERCENT_SIGN = True  # store "60%"


# =============================================================================
# Helpers
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"t6.s5.{h}"


def strip_heading_numbering(text: str) -> str:
    t = _s(text)
    if not t:
        return ""
    t = re.sub(r"^\s*\(?\d+(\.\d+)*\)?\s*[\.\)\-:]\s*", "", t)
    t = re.sub(r"^\s*\d+(\.\d+)*\s+", "", t)
    return t.strip()


def _safe_float(s: str) -> float:
    """
    Fast safe float parse.
    Accept: "12", "12.5", " 12 "
    """
    t = _s(s)
    if not t:
        return 0.0
    t = t.replace(",", "").strip()
    try:
        return float(t)
    except Exception:
        return 0.0


def _num_to_str(v: float) -> str:
    s = str(v)
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _titles_from_step3() -> List[str]:
    comps = st.session_state.get(SS_OBS, []) or []
    titles: List[str] = []

    for comp in comps:
        if not isinstance(comp, dict):
            continue
        obs_valid = comp.get("observations_valid") or []
        if not isinstance(obs_valid, list):
            continue
        for obs in obs_valid:
            if not isinstance(obs, dict):
                continue
            t = _s(obs.get("title"))
            if t:
                titles.append(t)

    # de-dup keep order
    seen = set()
    out: List[str] = []
    for t in titles:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _titles_hash(titles: List[str]) -> str:
    blob = "\n".join(titles).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()


def _default_rows_from_titles(titles: List[str]) -> List[Dict[str, str]]:
    if not titles:
        return [
            {"No.": str(i), "Activities": "", "Planned": "", "Achieved": "", "Progress": "", "Remarks": ""}
            for i in range(1, UIConfig.DEFAULT_EMPTY_ROWS + 1)
        ]

    rows: List[Dict[str, str]] = []
    for i, t in enumerate(titles, start=1):
        act = strip_heading_numbering(t) or t
        rows.append({"No.": str(i), "Activities": act, "Planned": "", "Achieved": "", "Progress": "", "Remarks": ""})
    return rows


def _normalize_rows(rows: Any) -> List[Dict[str, str]]:
    if not isinstance(rows, list):
        rows = []

    out: List[Dict[str, str]] = []
    for i, r in enumerate(rows, start=1):
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "No.": str(i),
                "Activities": _s(r.get("Activities")),
                "Planned": _s(r.get("Planned")),
                "Achieved": _s(r.get("Achieved")),
                "Progress": _s(r.get("Progress")),
                "Remarks": _s(r.get("Remarks")),
            }
        )

    if not out:
        out = _default_rows_from_titles([])

    for i, r in enumerate(out, start=1):
        r["No."] = str(i)

    return out


def _ensure_state() -> None:
    ss = st.session_state
    ss.setdefault(SS_WORK, [])
    if not isinstance(ss[SS_WORK], list):
        ss[SS_WORK] = []

    ss.setdefault(SS_AUTO_PROGRESS, False)
    if not isinstance(ss[SS_AUTO_PROGRESS], bool):
        ss[SS_AUTO_PROGRESS] = False

    ss.setdefault(SS_TITLES_HASH, "")


def _sync_rows_if_titles_changed() -> None:
    """
    ✅ Performance: sync from Step 3 only when titles changed.
    Keeps user-entered values when matching activities exist.
    """
    titles = _titles_from_step3()
    h = _titles_hash(titles)

    if st.session_state.get(SS_TITLES_HASH) == h:
        return  # no changes

    cur = _normalize_rows(st.session_state.get(SS_WORK, []))

    if not titles:
        if not cur:
            st.session_state[SS_WORK] = _default_rows_from_titles([])
        st.session_state[SS_TITLES_HASH] = h
        return

    by_act: Dict[str, Dict[str, str]] = {}
    for r in cur:
        act = _s(r.get("Activities"))
        if act:
            by_act[act] = r

    new_rows: List[Dict[str, str]] = []
    for i, t in enumerate(titles, start=1):
        act = strip_heading_numbering(t) or t
        if act in by_act:
            row = dict(by_act[act])
        else:
            row = {"No.": str(i), "Activities": act, "Planned": "", "Achieved": "", "Progress": "", "Remarks": ""}
        row["No."] = str(i)
        new_rows.append(row)

    # keep extra manual rows at bottom
    used = set(strip_heading_numbering(t) or t for t in titles)
    extras = [r for r in cur if _s(r.get("Activities")) and _s(r.get("Activities")) not in used]
    for r in extras:
        rr = dict(r)
        rr["No."] = str(len(new_rows) + 1)
        new_rows.append(rr)

    st.session_state[SS_WORK] = _normalize_rows(new_rows)
    st.session_state[SS_TITLES_HASH] = h


def _parse_progress_percent(progress_text: str) -> int:
    t = _s(progress_text)
    if not t:
        return 0
    t = t.replace("%", "").strip()
    try:
        n = int(float(t))
    except Exception:
        return 0
    return max(UIConfig.PROGRESS_MIN, min(UIConfig.PROGRESS_MAX, n))


def _format_progress(percent: int) -> str:
    p = max(UIConfig.PROGRESS_MIN, min(UIConfig.PROGRESS_MAX, int(percent)))
    return f"{p}%" if UIConfig.STORE_WITH_PERCENT_SIGN else str(p)


def _calc_progress(planned: float, achieved: float) -> int:
    if planned <= 0:
        return 0
    pct = int(round((achieved / planned) * 100.0))
    return max(UIConfig.PROGRESS_MIN, min(UIConfig.PROGRESS_MAX, pct))


def _add_empty_row() -> None:
    rows = _normalize_rows(st.session_state.get(SS_WORK, []))
    rows.append({"No.": str(len(rows) + 1), "Activities": "", "Planned": "", "Achieved": "", "Progress": "", "Remarks": ""})
    st.session_state[SS_WORK] = _normalize_rows(rows)


def _remove_row(idx_0based: int) -> None:
    rows = _normalize_rows(st.session_state.get(SS_WORK, []))
    if 0 <= idx_0based < len(rows):
        rows.pop(idx_0based)
    if not rows:
        rows = _default_rows_from_titles([])
    st.session_state[SS_WORK] = _normalize_rows(rows)


# =============================================================================
# Safe progress sync callbacks
# =============================================================================
def _sync_progress_from_slider(i: int) -> None:
    slider_key = _key("p_slider", i)
    number_key = _key("p_number", i)
    st.session_state[number_key] = int(st.session_state.get(slider_key, 0))


def _sync_progress_from_number(i: int) -> None:
    slider_key = _key("p_slider", i)
    number_key = _key("p_number", i)
    st.session_state[slider_key] = int(st.session_state.get(number_key, 0))


# =============================================================================
# Main render
# =============================================================================
def render_step(ctx: Tool6Context, **_) -> bool:
    _ = ctx
    _ensure_state()

    st.subheader("Step 5 — Work Progress Summary")

    with st.container(border=True):
        card_open(
            "Work Progress Summary during the Visit",
            subtitle=(
                "Activities are auto-filled from Step 3 (titles). "
                "Planned/Achieved are numeric. Progress can be manual or auto-calculated."
            ),
            variant="lg-variant-cyan",
        )

        # ✅ FAST sync only when Step 3 titles changed
        _sync_rows_if_titles_changed()

        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.2, 2.4], gap="small")

        with c1:
            if st.button("Reset from Step 3 titles", use_container_width=True, key=_key("reset")):
                titles = _titles_from_step3()
                st.session_state[SS_WORK] = _default_rows_from_titles(titles)
                st.session_state[SS_TITLES_HASH] = _titles_hash(titles)

        with c2:
            st.button("Add empty row", use_container_width=True, key=_key("add_row"), on_click=_add_empty_row)

        with c3:
            auto_calc_val = st.toggle(
                "Auto-calc Progress",
                value=bool(st.session_state.get(SS_AUTO_PROGRESS, False)),
                key=_key("auto_calc"),
                help="If ON: Progress is computed from Achieved/Planned and manual progress controls are disabled.",
            )
            st.session_state[SS_AUTO_PROGRESS] = bool(auto_calc_val)

        with c4:
            st.caption("Progress is stored exactly (e.g., 60%) and printed in the report.")

        st.divider()

        rows = _normalize_rows(st.session_state.get(SS_WORK, []))
        auto_calc = bool(st.session_state.get(SS_AUTO_PROGRESS, False))

        updated_rows: List[Dict[str, str]] = []

        for i, r in enumerate(rows):
            with st.container(border=True):
                h1, h2 = st.columns([6, 1], gap="small")
                with h1:
                    label = f"Row {i + 1}" if UIConfig.SHOW_ROW_NUMBERS else "Row"
                    st.markdown(f"**{label}**")
                with h2:
                    st.button("Remove", use_container_width=True, key=_key("rm", i), on_click=_remove_row, args=(i,))

                colA, colB, colC, colD, colE = st.columns([3.0, 1.2, 1.2, 2.2, 2.4], gap="small")

                with colA:
                    activities = st.text_input(
                        "Activities",
                        value=_s(r.get("Activities")),
                        key=_key("act", i),
                        placeholder="e.g., Construction of boundary wall",
                    )

                with colB:
                    planned_val = st.number_input(
                        "Planned",
                        min_value=UIConfig.VALUE_MIN,
                        value=float(_safe_float(_s(r.get("Planned")))),
                        step=float(UIConfig.VALUE_STEP),
                        format=UIConfig.VALUE_FORMAT,
                        key=_key("planned", i),
                    )

                with colC:
                    achieved_val = st.number_input(
                        "Achieved",
                        min_value=UIConfig.VALUE_MIN,
                        value=float(_safe_float(_s(r.get("Achieved")))),
                        step=float(UIConfig.VALUE_STEP),
                        format=UIConfig.VALUE_FORMAT,
                        key=_key("achieved", i),
                    )

                with colD:
                    if auto_calc:
                        pct = _calc_progress(float(planned_val), float(achieved_val))
                    else:
                        pct = _parse_progress_percent(_s(r.get("Progress")))

                    slider_key = _key("p_slider", i)
                    number_key = _key("p_number", i)

                    if slider_key not in st.session_state:
                        st.session_state[slider_key] = int(pct)
                    if number_key not in st.session_state:
                        st.session_state[number_key] = int(pct)

                    if auto_calc:
                        st.session_state[slider_key] = int(pct)
                        st.session_state[number_key] = int(pct)

                    st.slider(
                        "Progress (%)",
                        min_value=UIConfig.PROGRESS_MIN,
                        max_value=UIConfig.PROGRESS_MAX,
                        value=int(st.session_state[slider_key]),
                        step=UIConfig.PROGRESS_STEP,
                        key=slider_key,
                        disabled=auto_calc,
                        on_change=_sync_progress_from_slider,
                        args=(i,),
                    )

                    st.number_input(
                        "Progress value",
                        min_value=UIConfig.PROGRESS_MIN,
                        max_value=UIConfig.PROGRESS_MAX,
                        value=int(st.session_state[number_key]),
                        step=UIConfig.PROGRESS_STEP,
                        key=number_key,
                        disabled=auto_calc,
                        on_change=_sync_progress_from_number,
                        args=(i,),
                    )

                    final_pct = int(st.session_state.get(slider_key, int(pct)))

                with colE:
                    remarks = st.text_input(
                        "Remarks",
                        value=_s(r.get("Remarks")),
                        key=_key("remarks", i),
                        placeholder="Optional notes...",
                    )

                updated_rows.append(
                    {
                        "No.": str(i + 1),
                        "Activities": _s(activities),
                        "Planned": _num_to_str(float(planned_val)),
                        "Achieved": _num_to_str(float(achieved_val)),
                        "Progress": _format_progress(final_pct),
                        "Remarks": _s(remarks),
                    }
                )

        st.session_state[SS_WORK] = _normalize_rows(updated_rows)

        has_any = any(_s(r.get("Activities")) for r in st.session_state[SS_WORK])
        if has_any:
            status_card("Saved", "Work progress rows are stored and will be used in the report.", level="success")
        else:
            status_card("Table is empty", "Please enter at least one activity row.", level="warning")

        card_close()

    return bool(has_any)
