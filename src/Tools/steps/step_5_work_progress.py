# src/Tools/steps/step_5_work_progress.py
from __future__ import annotations

import hashlib
import io
import re
from typing import Any, Dict, List, Tuple

import streamlit as st

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_close, status_card


# =============================================================================
# Session keys (Tool6 naming)
# =============================================================================
SS_OBS = "tool6_obs_components"            # Step 3 output
SS_WORK = "tool6_work_progress_rows"       # Step 5 output rows
SS_AUTO_PROGRESS = "tool6_work_auto_progress"
SS_TITLES_HASH = "tool6_work_titles_hash"  # performance: detect titles changes

# UI/UX states
SS_VIEW_MODE = "tool6_work_view_mode"      # "Cards" | "Compact"
SS_SEARCH = "tool6_work_search"
SS_ROWS_PER_PAGE = "tool6_work_rows_per_page"
SS_PAGE = "tool6_work_page"
SS_COLLAPSE_ALL = "tool6_work_collapse_all"


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

    # Units
    UNIT_PRESETS = ["", "pcs", "m", "m²", "m³", "days", "months", "sessions", "sets", "liters", "kg", "Other…"]
    UNIT_OTHER_SENTINEL = "Other…"

    # Pagination
    ROWS_PER_PAGE_OPTIONS = [10, 20, 50, 100]


# =============================================================================
# Styling
# =============================================================================
def _inject_css() -> None:
    st.markdown(
        """
        <style>
          [data-testid="stVerticalBlock"] { gap: 0.70rem; }

          /* Card wrapper (Cards view) */
          .t6-rowcard {
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 14px;
            padding: 14px;
            background: rgba(255,255,255,0.02);
            margin: 10px 0 12px 0;
          }

          .t6-rowcard .t6-title {
            font-weight: 700;
            margin-bottom: 6px;
          }

          /* Small toolbar buttons align nicely */
          .t6-btnrow [data-testid="stHorizontalBlock"] {
            align-items: center;
          }

          /* Compact expander extra spacing */
          div[data-testid="stExpander"] > details {
            border-radius: 14px !important;
          }

          /* Make inputs look aligned */
          div[data-testid="stTextInput"] input,
          div[data-testid="stTextArea"] textarea,
          div[data-testid="stSelectbox"] div[role="combobox"],
          div[data-testid="stNumberInput"] input {
            width: 100% !important;
          }

          /* Slightly tighter labels in dense areas */
          label, .st-emotion-cache-1p1nwyz, .st-emotion-cache-1y4p8pa {
            line-height: 1.15;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


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


def _default_row(i: int) -> Dict[str, str]:
    return {
        "No.": str(i),
        "Activities": "",
        "Planned": "",
        "Planned Unit": "",
        "Achieved": "",
        "Achieved Unit": "",
        "Progress": "",
        "Remarks": "",
        "Override Progress": "0",  # "0"/"1"
    }


def _default_rows_from_titles(titles: List[str]) -> List[Dict[str, str]]:
    if not titles:
        return [_default_row(i) for i in range(1, UIConfig.DEFAULT_EMPTY_ROWS + 1)]

    rows: List[Dict[str, str]] = []
    for i, t in enumerate(titles, start=1):
        act = strip_heading_numbering(t) or t
        r = _default_row(i)
        r["Activities"] = act
        rows.append(r)
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
                "Planned Unit": _s(r.get("Planned Unit")),
                "Achieved": _s(r.get("Achieved")),
                "Achieved Unit": _s(r.get("Achieved Unit")),
                "Progress": _s(r.get("Progress")),
                "Remarks": _s(r.get("Remarks")),
                "Override Progress": "1" if _s(r.get("Override Progress")) in ("1", "true", "True", "yes", "Yes") else "0",
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

    ss.setdefault(SS_VIEW_MODE, "Cards")
    if ss[SS_VIEW_MODE] not in ("Cards", "Compact"):
        ss[SS_VIEW_MODE] = "Cards"

    ss.setdefault(SS_SEARCH, "")
    ss.setdefault(SS_ROWS_PER_PAGE, 20)
    if ss[SS_ROWS_PER_PAGE] not in UIConfig.ROWS_PER_PAGE_OPTIONS:
        ss[SS_ROWS_PER_PAGE] = 20

    ss.setdefault(SS_PAGE, 1)
    if not isinstance(ss[SS_PAGE], int) or ss[SS_PAGE] < 1:
        ss[SS_PAGE] = 1

    ss.setdefault(SS_COLLAPSE_ALL, False)
    if not isinstance(ss[SS_COLLAPSE_ALL], bool):
        ss[SS_COLLAPSE_ALL] = False


def _sync_rows_if_titles_changed() -> None:
    """
    ✅ Sync from Step 3 only when titles changed.
    Keeps user-entered values when matching activities exist.
    """
    titles = _titles_from_step3()
    h = _titles_hash(titles)

    if st.session_state.get(SS_TITLES_HASH) == h:
        return

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
            row = _default_row(i)
            row["Activities"] = act
        row["No."] = str(i)
        new_rows.append(row)

    # Keep extra manual rows at bottom
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
    rows.append(_default_row(len(rows) + 1))
    st.session_state[SS_WORK] = _normalize_rows(rows)


def _remove_row(idx_0based: int) -> None:
    rows = _normalize_rows(st.session_state.get(SS_WORK, []))
    if 0 <= idx_0based < len(rows):
        rows.pop(idx_0based)
    if not rows:
        rows = _default_rows_from_titles([])
    st.session_state[SS_WORK] = _normalize_rows(rows)


def _duplicate_row(idx_0based: int) -> None:
    rows = _normalize_rows(st.session_state.get(SS_WORK, []))
    if 0 <= idx_0based < len(rows):
        copy_row = dict(rows[idx_0based])
        copy_row["No."] = ""
        rows.insert(idx_0based + 1, copy_row)
    st.session_state[SS_WORK] = _normalize_rows(rows)


def _move_row(idx_0based: int, direction: int) -> None:
    rows = _normalize_rows(st.session_state.get(SS_WORK, []))
    j = idx_0based + direction
    if 0 <= idx_0based < len(rows) and 0 <= j < len(rows):
        rows[idx_0based], rows[j] = rows[j], rows[idx_0based]
    st.session_state[SS_WORK] = _normalize_rows(rows)


# =============================================================================
# Safe progress sync callbacks
# =============================================================================
def _sync_progress_from_slider(i_global: int) -> None:
    slider_key = _key("p_slider", i_global)
    number_key = _key("p_number", i_global)
    st.session_state[number_key] = int(st.session_state.get(slider_key, 0))


def _sync_progress_from_number(i_global: int) -> None:
    slider_key = _key("p_slider", i_global)
    number_key = _key("p_number", i_global)
    st.session_state[slider_key] = int(st.session_state.get(number_key, 0))


# =============================================================================
# CSV import/export
# =============================================================================
CSV_COLUMNS = [
    "Activities",
    "Planned",
    "Planned Unit",
    "Achieved",
    "Achieved Unit",
    "Progress",
    "Remarks",
    "Override Progress",
]



# =============================================================================
# Validation + filtering + pagination
# =============================================================================
def _row_warnings(planned: float, achieved: float, p_unit: str, a_unit: str) -> List[str]:
    w: List[str] = []
    if planned == 0 and achieved > 0:
        w.append("Planned is 0 while Achieved > 0 (progress will be 0%).")
    if planned > 0 and achieved > planned:
        w.append("Achieved exceeds Planned.")
    if (_s(p_unit) and not _s(a_unit)) or (not _s(p_unit) and _s(a_unit)):
        w.append("Unit mismatch (one side is empty).")
    if _s(p_unit) and _s(a_unit) and _s(p_unit) != _s(a_unit):
        w.append("Units differ between Planned and Achieved.")
    return w


def _apply_search_filter(rows: List[Dict[str, str]], query: str) -> List[int]:
    q = _s(query).lower()
    if not q:
        return list(range(len(rows)))
    idxs: List[int] = []
    for i, r in enumerate(rows):
        if q in _s(r.get("Activities")).lower():
            idxs.append(i)
    return idxs


def _paginate(indices: List[int], rows_per_page: int, page: int) -> Tuple[List[int], int]:
    total = len(indices)
    if rows_per_page <= 0:
        return indices, 1
    total_pages = max(1, (total + rows_per_page - 1) // rows_per_page)
    page = max(1, min(total_pages, page))
    start = (page - 1) * rows_per_page
    end = start + rows_per_page
    return indices[start:end], total_pages


# =============================================================================
# Unit selector
# =============================================================================
def _unit_picker(label: str, current_unit: str, key_prefix: str) -> str:
    cur = _s(current_unit)

    if cur in UIConfig.UNIT_PRESETS:
        sel = cur
        other_val = ""
    else:
        sel = UIConfig.UNIT_OTHER_SENTINEL
        other_val = cur

    sel_key = _key(key_prefix, "unit_sel")
    other_key = _key(key_prefix, "unit_other")

    if sel_key not in st.session_state:
        st.session_state[sel_key] = sel
    if other_key not in st.session_state:
        st.session_state[other_key] = other_val

    selected = st.selectbox(label, options=UIConfig.UNIT_PRESETS, key=sel_key)
    if selected == UIConfig.UNIT_OTHER_SENTINEL:
        custom = st.text_input("Custom", key=other_key, placeholder="e.g., bags")
        return _s(custom)
    return _s(selected)


# =============================================================================
# MAIN
# =============================================================================
def render_step(ctx: Tool6Context, **_) -> bool:
    _ = ctx
    _ensure_state()
    _inject_css()

    with st.container(border=True):
        # ✅ Sync only when titles changed
        _sync_rows_if_titles_changed()

        # ---- Top controls ----
        c1, c2, c3, c4, c5 = st.columns([1.2, 1.2, 1.4, 1.4, 2.0], gap="small")

        with c1:
            if st.button("Reset from Step 3 titles", use_container_width=True, key=_key("reset")):
                titles = _titles_from_step3()
                st.session_state[SS_WORK] = _default_rows_from_titles(titles)
                st.session_state[SS_TITLES_HASH] = _titles_hash(titles)
                st.session_state[SS_PAGE] = 1
                st.rerun()

        with c2:
            st.button("Add empty row", use_container_width=True, key=_key("add_row"), on_click=_add_empty_row)

        with c3:
            auto_calc_val = st.toggle(
                "Auto-calc Progress",
                value=bool(st.session_state.get(SS_AUTO_PROGRESS, False)),
                key=_key("auto_calc"),
            )
            st.session_state[SS_AUTO_PROGRESS] = bool(auto_calc_val)

        with c4:
            view_mode = st.segmented_control(
                "View",
                options=["Cards", "Compact"],
                default=st.session_state.get(SS_VIEW_MODE, "Cards"),
                key=_key("view_mode"),
            )
            st.session_state[SS_VIEW_MODE] = view_mode or "Cards"

        with c5:
            search_q = st.text_input(
                "Search Activities",
                value=_s(st.session_state.get(SS_SEARCH, "")),
                key=_key("search"),
                placeholder="Type to filter…",
            )
            # اگر کاربر چیزی نوشت، صفحه را ۱ کن
            if _s(search_q) != _s(st.session_state.get(SS_SEARCH, "")):
                st.session_state[SS_PAGE] = 1
            st.session_state[SS_SEARCH] = _s(search_q)

        st.divider()

        # ---- Rows + KPIs ----
        rows = _normalize_rows(st.session_state.get(SS_WORK, []))
        auto_calc = bool(st.session_state.get(SS_AUTO_PROGRESS, False))

        planned_sum = 0.0
        achieved_sum = 0.0
        warn_count = 0
        avg_progress_sum = 0

        for r in rows:
            p = _safe_float(_s(r.get("Planned")))
            a = _safe_float(_s(r.get("Achieved")))
            planned_sum += p
            achieved_sum += a
            pct = _parse_progress_percent(_s(r.get("Progress")))
            avg_progress_sum += pct
            if _row_warnings(p, a, _s(r.get("Planned Unit")), _s(r.get("Achieved Unit"))):
                warn_count += 1

        total_rows = len(rows)
        avg_progress = (avg_progress_sum / total_rows) if total_rows else 0.0

        k1, k2, k3, k4 = st.columns(4, gap="small")
        k1.metric("Rows", str(total_rows))
        k2.metric("Total Planned", _num_to_str(float(planned_sum)))
        k3.metric("Total Achieved", _num_to_str(float(achieved_sum)))
        k4.metric("Warnings", str(warn_count))

        st.divider()



        # ---- Filter + paginate ----
        filtered_indices = _apply_search_filter(rows, _s(st.session_state.get(SS_SEARCH, "")))
        page = int(st.session_state.get(SS_PAGE, 1))
        rpp = int(st.session_state.get(SS_ROWS_PER_PAGE, 20))
        page_indices, total_pages = _paginate(filtered_indices, rpp, page)
        st.session_state[SS_PAGE] = max(1, min(total_pages, page))

        st.divider()

        # ---- Render rows ----
        updated_rows = list(rows)
        view_mode = st.session_state.get(SS_VIEW_MODE, "Cards")
        collapse_all = bool(st.session_state.get(SS_COLLAPSE_ALL, False))

        for i_global in page_indices:
            r = rows[i_global]

            # ✅ ALWAYS define container_ctx (fixes UnboundLocalError)
            if view_mode == "Compact":
                header = f"Row {i_global + 1}: {_s(r.get('Activities')) or '(no activity)'}"
                container_ctx = st.expander(header, expanded=not collapse_all)
                card_wrap = False
            else:
                container_ctx = st.container()
                card_wrap = True

            with container_ctx:
                if card_wrap:
                    st.markdown("<div class='t6-rowcard'>", unsafe_allow_html=True)
                    title = f"Row {i_global + 1}" if UIConfig.SHOW_ROW_NUMBERS else "Row"
                    st.markdown(f"<div class='t6-title'>{title}</div>", unsafe_allow_html=True)

                # Actions row
                st.markdown("<div class='t6-btnrow'>", unsafe_allow_html=True)
                h1, h2, h3, h4, h5 = st.columns([4.8, 1.2, 1.2, 1.2, 1.2], gap="small")
                with h1:
                    st.caption(_s(r.get("Activities")) or "(no activity)")
                with h2:
                    st.button("Duplicate", use_container_width=True, key=_key("dup", i_global), on_click=_duplicate_row, args=(i_global,))
                with h3:
                    st.button("Up", use_container_width=True, key=_key("up", i_global), on_click=_move_row, args=(i_global, -1), disabled=(i_global == 0))
                with h4:
                    st.button("Down", use_container_width=True, key=_key("down", i_global), on_click=_move_row, args=(i_global, +1), disabled=(i_global == (len(rows) - 1)))
                with h5:
                    st.button("Remove", use_container_width=True, key=_key("rm", i_global), on_click=_remove_row, args=(i_global,))
                st.markdown("</div>", unsafe_allow_html=True)

                # Main inputs
                colA, colB, colC, colD, colE = st.columns([3.2, 2.4, 2.4, 2.2, 2.8], gap="small")

                with colA:
                    activities = st.text_input(
                        "Activities",
                        value=_s(r.get("Activities")),
                        key=_key("act", i_global),
                        placeholder="e.g., Construction of boundary wall",
                    )

                with colB:
                    p1, p2 = st.columns([2.0, 1.5], gap="small")
                    with p1:
                        planned_val = st.number_input(
                            "Planned",
                            min_value=UIConfig.VALUE_MIN,
                            value=float(_safe_float(_s(r.get("Planned")))),
                            step=float(UIConfig.VALUE_STEP),
                            format=UIConfig.VALUE_FORMAT,
                            key=_key("planned", i_global),
                        )
                    with p2:
                        planned_unit = _unit_picker(
                            "Planned Unit",
                            current_unit=_s(r.get("Planned Unit")),
                            key_prefix=f"planned_unit.{i_global}",
                        )

                with colC:
                    a1, a2 = st.columns([2.0, 1.5], gap="small")
                    with a1:
                        achieved_val = st.number_input(
                            "Achieved",
                            min_value=UIConfig.VALUE_MIN,
                            value=float(_safe_float(_s(r.get("Achieved")))),
                            step=float(UIConfig.VALUE_STEP),
                            format=UIConfig.VALUE_FORMAT,
                            key=_key("achieved", i_global),
                        )
                    with a2:
                        achieved_unit = _unit_picker(
                            "Achieved Unit",
                            current_unit=_s(r.get("Achieved Unit")),
                            key_prefix=f"achieved_unit.{i_global}",
                        )

                with colD:
                    override_key = _key("override", i_global)
                    if override_key not in st.session_state:
                        st.session_state[override_key] = (_s(r.get("Override Progress")) == "1")

                    override_manual = st.toggle(
                        "Override manual progress",
                        value=bool(st.session_state[override_key]),
                        key=override_key,
                        help="If ON (and Auto-calc is ON): this row allows manual progress entry.",
                    )

                    row_is_auto = bool(auto_calc) and (not bool(override_manual))
                    pct = _calc_progress(float(planned_val), float(achieved_val)) if row_is_auto else _parse_progress_percent(_s(r.get("Progress")))

                    slider_key = _key("p_slider", i_global)
                    number_key = _key("p_number", i_global)

                    if slider_key not in st.session_state:
                        st.session_state[slider_key] = int(pct)
                    if number_key not in st.session_state:
                        st.session_state[number_key] = int(pct)

                    if row_is_auto:
                        st.session_state[slider_key] = int(pct)
                        st.session_state[number_key] = int(pct)

                    st.slider(
                        "Progress (%)",
                        min_value=UIConfig.PROGRESS_MIN,
                        max_value=UIConfig.PROGRESS_MAX,
                        value=int(st.session_state[slider_key]),
                        step=UIConfig.PROGRESS_STEP,
                        key=slider_key,
                        disabled=row_is_auto,
                        on_change=_sync_progress_from_slider,
                        args=(i_global,),
                    )

                    st.number_input(
                        "Progress value",
                        min_value=UIConfig.PROGRESS_MIN,
                        max_value=UIConfig.PROGRESS_MAX,
                        value=int(st.session_state[number_key]),
                        step=UIConfig.PROGRESS_STEP,
                        key=number_key,
                        disabled=row_is_auto,
                        on_change=_sync_progress_from_number,
                        args=(i_global,),
                    )

                    final_pct = int(st.session_state.get(slider_key, int(pct)))
                    st.progress(final_pct / 100.0)

                with colE:
                    remarks = st.text_input(
                        "Remarks",
                        value=_s(r.get("Remarks")),
                        key=_key("remarks", i_global),
                        placeholder="Optional notes...",
                    )

                warn_list = _row_warnings(
                    planned=float(planned_val),
                    achieved=float(achieved_val),
                    p_unit=_s(planned_unit),
                    a_unit=_s(achieved_unit),
                )
                if warn_list:
                    for w in warn_list:
                        st.warning(w)

                updated_rows[i_global] = {
                    "No.": str(i_global + 1),
                    "Activities": _s(activities),
                    "Planned": _num_to_str(float(planned_val)),
                    "Planned Unit": _s(planned_unit),
                    "Achieved": _num_to_str(float(achieved_val)),
                    "Achieved Unit": _s(achieved_unit),
                    "Progress": _format_progress(int(final_pct)),
                    "Remarks": _s(remarks),
                    "Override Progress": "1" if bool(override_manual) else "0",
                }

                if card_wrap:
                    st.markdown("</div>", unsafe_allow_html=True)

        # Store back
        st.session_state[SS_WORK] = _normalize_rows(updated_rows)

        # Status
        has_any = any(_s(r.get("Activities")) for r in st.session_state[SS_WORK])
        if has_any:
            if warn_count > 0:
                status_card(
                    "Saved (with warnings)",
                    "Rows are stored. Some rows have validation warnings—please review.",
                    level="warning",
                )
            else:
                status_card("Saved", "Work progress rows are stored and will be used in the report.", level="success")
        else:
            status_card("Table is empty", "Please enter at least one activity row.", level="warning")

        card_close()

    return bool(has_any)
