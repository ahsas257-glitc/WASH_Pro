# src/Tools/steps/step_2_general_info.py
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Dict, Tuple, List, Optional, Any

import streamlit as st

from src.Tools.utils.types import Tool6Context


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
DATE_FORMATS: Dict[str, str] = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD/MM/YYYY": "%d/%m/%Y",
    "DD-MMM-YYYY": "%d-%b-%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
}
DATE_FORMAT_LABELS: List[str] = list(DATE_FORMATS.keys())

YES_NO: List[str] = ["Yes", "No"]
CURRENCIES: List[str] = ["AFN", "USD", "EUR", "PKR", "IRR"]

_EMAIL_RE = re.compile(
    r"^(?=.{1,254}$)(?=.{1,64}@)[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)
_DIGITS_RE = re.compile(r"\D+")

SS_OVERRIDES = "general_info_overrides"
SS_DATEFMTS = "general_info_date_formats"
SS_MONEY_CUR = "general_info_cost_currency"
SS_MONEY_AMT = "general_info_cost_amount"
SS_CSS_ONCE = "_t6_step2_css_once"
SS_LAST_TOAST = "_t6_step2_last_toast"  # throttle toasts


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _md5_10(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:10]


def _k(field: str, suffix: str) -> str:
    return f"t6.s2.{_md5_10(field)}.{suffix}"


def _cols2(gap: str = "large"):
    return st.columns([1, 1], gap=gap)


def _section_title(text: str) -> None:
    st.markdown(f"### {text}")


def _inject_css_once() -> None:
    if st.session_state.get(SS_CSS_ONCE):
        return
    st.session_state[SS_CSS_ONCE] = True
    st.markdown(
        """
        <style>
          div[data-testid="stTextInput"] input,
          div[data-testid="stTextArea"] textarea,
          div[data-testid="stNumberInput"] input,
          div[data-testid="stSelectbox"] div[role="combobox"],
          div[data-testid="stDateInput"] input { width: 100% !important; }

          [data-testid="stVerticalBlock"] { gap: 0.70rem; }
          .stCaption { margin-top: -6px; }

          button[data-baseweb="tab"] { padding: 8px 12px; }

          @media (max-width: 700px){
            .block-container { padding-left: 1rem; padding-right: 1rem; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _init_state() -> None:
    ss = st.session_state
    ss.setdefault(SS_OVERRIDES, {})
    ss.setdefault(SS_DATEFMTS, {})
    ss.setdefault(SS_MONEY_CUR, {})
    ss.setdefault(SS_MONEY_AMT, {})
    ss.setdefault(SS_LAST_TOAST, 0.0)


def _get_default(field: str, ctx: Tool6Context) -> str:
    return _s((ctx.defaults or {}).get(field, ""))


def _get_value(field: str, ctx: Tool6Context) -> str:
    overrides = st.session_state.get(SS_OVERRIDES, {}) or {}
    return _s(overrides.get(field, _get_default(field, ctx)))


def _show_hint(field: str, ctx: Tool6Context) -> None:
    hint = _s((ctx.hints or {}).get(field, ""))
    if hint:
        st.caption(hint)


def _toast_saved(msg: str = "Saved") -> None:
    # throttle toasts so UI feels stable
    now = datetime.utcnow().timestamp()
    last = float(st.session_state.get(SS_LAST_TOAST, 0.0))
    if now - last < 0.6:
        return
    st.session_state[SS_LAST_TOAST] = now
    st.toast(msg, icon="✅")


def _set_override_if_changed(field: str, value: str) -> None:
    ss = st.session_state
    overrides = ss.get(SS_OVERRIDES, {}) or {}
    if not isinstance(overrides, dict):
        overrides = {}

    newv = _s(value)
    oldv = _s(overrides.get(field, ""))

    if newv == oldv:
        return

    overrides[field] = newv
    ss[SS_OVERRIDES] = overrides
    _toast_saved(f"{field} saved")


def _ensure_widget_default(widget_key: str, default_value: Any) -> None:
    ss = st.session_state
    if widget_key not in ss:
        ss[widget_key] = default_value


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------
def validate_email(email: str) -> Tuple[bool, str]:
    e = _s(email)
    if not e:
        return True, ""
    if " " in e:
        return False, "Email must not contain spaces."
    if ".." in e:
        return False, "Email contains consecutive dots (..)."
    if not _EMAIL_RE.match(e):
        return False, "Invalid email format. Example: name@example.com"
    domain = e.split("@", 1)[1]
    for label in domain.split("."):
        if label.startswith("-") or label.endswith("-"):
            return False, "Invalid domain label (cannot start/end with hyphen)."
    return True, ""


# -----------------------------------------------------------------------------
# Date helpers
# -----------------------------------------------------------------------------
def _cover_date_format_label() -> str:
    raw = st.session_state.get("cover_date_format", "%Y-%m-%d")
    raw_s = _s(raw)
    if raw_s in DATE_FORMATS:
        return raw_s
    for label, fmt in DATE_FORMATS.items():
        if raw_s == fmt:
            return label
    return "YYYY-MM-DD"


def _parse_date_guess(raw: str) -> Optional[date]:
    t = _s(raw)
    if not t:
        return None
    t = t.replace("T", " ").split(" ")[0].strip()
    formats = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%b-%Y", "%d-%B-%Y", "%Y/%m/%d")
    for fmt in formats:
        try:
            return datetime.strptime(t, fmt).date()
        except Exception:
            pass
    return None


def _apply_date_override(field: str, *, date_key: str, fmt_key: str) -> None:
    ss = st.session_state
    picked: date = ss.get(date_key) or date.today()

    chosen_label = _s(ss.get(fmt_key))
    if chosen_label not in DATE_FORMATS:
        chosen_label = _cover_date_format_label()
        ss[fmt_key] = chosen_label

    formatted = picked.strftime(DATE_FORMATS[chosen_label])

    per_field: Dict[str, str] = ss.get(SS_DATEFMTS, {}) or {}
    per_field[field] = chosen_label
    ss[SS_DATEFMTS] = per_field

    _set_override_if_changed(field, formatted)


# -----------------------------------------------------------------------------
# Phone helpers
# -----------------------------------------------------------------------------
def _only_digits(v: str) -> str:
    return _DIGITS_RE.sub("", _s(v))


def _extract_af_9digits(raw: str) -> str:
    d = _only_digits(raw)
    if not d:
        return ""
    if d.startswith("0093"):
        d = d[4:]
    elif d.startswith("93"):
        d = d[2:]
    if len(d) == 10 and d.startswith("0"):
        d = d[1:]
    if len(d) > 9:
        d = d[-9:]
    return d


# -----------------------------------------------------------------------------
# Money helpers
# -----------------------------------------------------------------------------
def _init_money_from_existing(raw: str) -> Tuple[float, str]:
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{3})\s*$", _s(raw))
    if m:
        try:
            amt = float(m.group(1))
        except Exception:
            amt = 0.0
        cur = m.group(2).upper()
        return amt, (cur if cur in CURRENCIES else "AFN")
    return 0.0, "AFN"


def _apply_money_override(field: str, *, amt_key: str, cur_key: str) -> None:
    ss = st.session_state
    amt = float(ss.get(amt_key) or 0.0)
    cur = _s(ss.get(cur_key)) or "AFN"
    if cur not in CURRENCIES:
        cur = "AFN"
        ss[cur_key] = cur

    if amt > 0:
        amount_str = f"{amt:.2f}".rstrip("0").rstrip(".")
        _set_override_if_changed(field, f"{amount_str} {cur}")
    else:
        _set_override_if_changed(field, "")


# -----------------------------------------------------------------------------
# Widgets (SUPER FAST FEEL)
# -----------------------------------------------------------------------------
def w_text(field: str, ctx: Tool6Context, *, placeholder: str = "", help_text: str = "") -> None:
    k = _k(field, "text")
    _ensure_widget_default(k, _get_value(field, ctx))

    st.text_input(
        field,
        key=k,
        placeholder=placeholder,
        help=help_text or None,
        # default behaviour: triggers on enter/blur, not every keystroke
        on_change=lambda: _set_override_if_changed(field, _s(st.session_state.get(k))),
    )
    _show_hint(field, ctx)


def w_select(field: str, ctx: Tool6Context, options: List[str], *, allow_empty: bool = True, help_text: str = "") -> None:
    cur = _get_value(field, ctx)
    opts = ([""] + options) if allow_empty else options
    if cur not in opts:
        cur = opts[0] if opts else ""

    k = _k(field, "select")
    _ensure_widget_default(k, cur)

    st.selectbox(
        field,
        options=opts,
        key=k,
        help=help_text or None,
        on_change=lambda: _set_override_if_changed(field, _s(st.session_state.get(k))),
    )
    _show_hint(field, ctx)


def w_yes_no(field: str, ctx: Tool6Context, *, allow_empty: bool = True) -> None:
    w_select(field, ctx, YES_NO, allow_empty=allow_empty)


def w_percent(field: str, ctx: Tool6Context) -> None:
    cur = _get_value(field, ctx)
    try:
        cur_f = float(cur) if _s(cur) else 0.0
    except Exception:
        cur_f = 0.0

    k = _k(field, "percent")
    _ensure_widget_default(k, float(cur_f))

    st.number_input(
        field,
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        key=k,
        help="Enter a value from 0 to 100.",
        on_change=lambda: _set_override_if_changed(field, f"{float(st.session_state.get(k) or 0.0):.0f}"),
    )
    _show_hint(field, ctx)


def w_email(field: str, ctx: Tool6Context, *, placeholder: str = "name@example.com") -> None:
    k = _k(field, "email")
    _ensure_widget_default(k, _get_value(field, ctx))

    st.text_input(
        field,
        key=k,
        placeholder=placeholder,
        help="Please enter a valid email address.",
        on_change=lambda: _set_override_if_changed(field, _s(st.session_state.get(k))),
    )

    val = _s(st.session_state.get(k))
    ok, msg = validate_email(val)
    if (not ok) and val:
        st.error(f"Invalid email: {msg}")
    else:
        _show_hint(field, ctx)


def w_af_phone(field: str, ctx: Tool6Context) -> None:
    raw = _get_value(field, ctx)
    nine = _extract_af_9digits(raw)

    k = _k(field, "phone9")
    _ensure_widget_default(k, nine)

    st.text_input(
        field,
        key=k,
        placeholder="9 digits (e.g., 701234567)",
        help="Enter 9 digits only. Leading 0 will be removed automatically.",
        on_change=lambda: _set_override_if_changed(
            field,
            (f"+93{_extract_af_9digits(_s(st.session_state.get(k)))}"
             if _extract_af_9digits(_s(st.session_state.get(k))) else "")
        ),
    )

    nine2 = _extract_af_9digits(_s(st.session_state.get(k)))
    if nine2 and len(nine2) != 9:
        st.warning("Phone number must be exactly 9 digits after +93.")

    _show_hint(field, ctx)


def w_date(field: str, ctx: Tool6Context) -> None:
    cover_label = _cover_date_format_label()

    per_field: Dict[str, str] = st.session_state.get(SS_DATEFMTS, {}) or {}
    chosen_label = _s(per_field.get(field, cover_label))
    if chosen_label not in DATE_FORMATS:
        chosen_label = cover_label

    cur_raw = _get_value(field, ctx)
    cur_dt = _parse_date_guess(cur_raw) or date.today()

    dk = _k(field, "date")
    fk = _k(field, "datefmt")
    _ensure_widget_default(dk, cur_dt)
    _ensure_widget_default(fk, chosen_label)

    c1, c2 = st.columns([2.2, 1.0], gap="small")
    with c1:
        st.date_input(
            field,
            key=dk,
            on_change=_apply_date_override,
            kwargs={"field": field, "date_key": dk, "fmt_key": fk},
        )
    with c2:
        st.selectbox(
            "Format",
            options=DATE_FORMAT_LABELS,
            key=fk,
            help="This format affects only this field (cover will not change).",
            on_change=_apply_date_override,
            kwargs={"field": field, "date_key": dk, "fmt_key": fk},
        )

    st.caption(f"Cover: {cover_label} • Field: {_s(st.session_state.get(fk))}")
    _show_hint(field, ctx)

    # apply once (cheap)
    if field not in (st.session_state.get(SS_OVERRIDES, {}) or {}):
        _apply_date_override(field, date_key=dk, fmt_key=fk)


def w_money(field: str, ctx: Tool6Context) -> None:
    raw = _get_value(field, ctx)

    amt_state: Dict[str, float] = st.session_state.get(SS_MONEY_AMT, {}) or {}
    cur_state: Dict[str, str] = st.session_state.get(SS_MONEY_CUR, {}) or {}

    if field not in amt_state or field not in cur_state:
        amt, cur = _init_money_from_existing(raw)
        amt_state[field] = amt
        cur_state[field] = cur
        st.session_state[SS_MONEY_AMT] = amt_state
        st.session_state[SS_MONEY_CUR] = cur_state

    ak = _k(field, "amount")
    ck = _k(field, "currency")
    _ensure_widget_default(ak, float(amt_state.get(field, 0.0)))
    _ensure_widget_default(ck, _s(cur_state.get(field, "AFN")))

    c1, c2 = st.columns([2.2, 1.0], gap="small")
    with c1:
        st.number_input(
            field,
            min_value=0.0,
            step=1.0,
            key=ak,
            help="Enter the amount.",
            on_change=_apply_money_override,
            kwargs={"field": field, "amt_key": ak, "cur_key": ck},
        )
    with c2:
        st.selectbox(
            "Currency",
            options=CURRENCIES,
            key=ck,
            on_change=_apply_money_override,
            kwargs={"field": field, "amt_key": ak, "cur_key": ck},
        )

    _show_hint(field, ctx)

    if field not in (st.session_state.get(SS_OVERRIDES, {}) or {}):
        _apply_money_override(field, amt_key=ak, cur_key=ck)


# -----------------------------------------------------------------------------
# Fragmented tabs (reduces UI churn)
# -----------------------------------------------------------------------------
@st.fragment
def _tab_project(ctx: Tool6Context) -> None:
    _section_title("Project Details")

    left, right = _cols2()
    with left:
        w_text("Province", ctx)
        w_text("District", ctx)
        w_text("Village / Community", ctx)
        w_text("GPS points", ctx, placeholder="e.g., 34.555, 69.207")
        w_text("Project Name", ctx)

    with right:
        w_date("Date of Visit", ctx)
        w_money("Estimated Project Cost", ctx)
        w_money("Contracted Project Cost", ctx)
        w_select("Project Status", ctx, ["Ongoing", "Completed", "Suspended"], allow_empty=True)
        w_select("Project progress", ctx, ["Ahead of Schedule", "On Schedule", "Running behind"], allow_empty=True)

    st.divider()
    _section_title("Contract & Progress")

    c1, c2 = _cols2()
    with c1:
        w_date("Contract Start Date", ctx)
    with c2:
        w_date("Contract End Date", ctx)

    c3, c4 = _cols2()
    with c3:
        w_percent("Previous Physical Progress (%)", ctx)
    with c4:
        w_percent("Current Physical Progress (%)", ctx)


@st.fragment
def _tab_respondent(ctx: Tool6Context) -> None:
    _section_title("Respondent / Participant")

    w_text("Name of the respondent (Participant / UNICEF / IPs)", ctx)

    c1, c2 = _cols2(gap="large")
    with c1:
        w_select("Sex of Respondent", ctx, ["Male", "Female"], allow_empty=True)
        w_af_phone("Contact Number of the Respondent", ctx)
    with c2:
        w_email("Email Address of the Respondent", ctx)


@st.fragment
def _tab_monitoring(ctx: Tool6Context) -> None:
    _section_title("Monitoring & Reporting")

    left, right = _cols2()
    with left:
        w_text("Name of the IP, Organization / NGO", ctx)
        w_text("Name of the monitor engineer", ctx)
        w_email("Email of the monitor engineer", ctx)

    with right:
        w_text("Monitoring Report Number", ctx)
        w_date("Date of Current Report", ctx)
        w_date("Date of Last Monitoring Report", ctx)
        w_text("Number of Sites Visited", ctx, placeholder="e.g., 3")


@st.fragment
def _tab_status_other(ctx: Tool6Context) -> None:
    _section_title("Status / Risk / Other")

    left, right = _cols2()
    with left:
        w_text("Reason for delay", ctx)
        w_text("CDC Code", ctx)
        w_text("Donor Name", ctx)

    with right:
        w_yes_no("Community agreement (Is the community/user group agreed on the well site?)", ctx, allow_empty=True)
        w_yes_no("Work safety considered", ctx, allow_empty=True)
        w_yes_no("Environmental risk", ctx, allow_empty=True)

    st.divider()
    _section_title("Available documents on site")

    d1, d2 = _cols2()
    docs_left = ["Contract", "Journal", "BOQ", "Design drawings"]
    docs_right = ["Site engineer", "Geophysical tests", "Water quality tests", "Pump test results"]

    with d1:
        for f in docs_left:
            w_yes_no(f, ctx, allow_empty=True)
    with d2:
        for f in docs_right:
            w_yes_no(f, ctx, allow_empty=True)


# -----------------------------------------------------------------------------
# Main render
# -----------------------------------------------------------------------------
def render_step(ctx: Tool6Context) -> bool:
    _init_state()
    _inject_css_once()

    tabs = st.tabs(["Project", "Respondent", "Monitoring", "Status / Other"])
    with tabs[0]:
        _tab_project(ctx)
    with tabs[1]:
        _tab_respondent(ctx)
    with tabs[2]:
        _tab_monitoring(ctx)
    with tabs[3]:
        _tab_status_other(ctx)

    # NO heavy status cards here (they cause visual jitter)
    st.caption("✅ Changes apply instantly. (Saved automatically)")

    return True
