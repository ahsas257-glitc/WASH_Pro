# src/Tools/steps/step_2_general_info.py
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Dict, Tuple, List, Optional, Any

import streamlit as st

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card


# -----------------------------------------------------------------------------
# Constants (compiled once)
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

_FORM_ID = "t6_step2_general_info_form"


# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _md5_10(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:10]


def _key(field: str, suffix: str) -> str:
    return f"t6.s2.{_md5_10(field)}.{suffix}"


def _cols2(gap: str = "large"):
    """2-column layout; Streamlit stacks automatically on small screens."""
    return st.columns([1, 1], gap=gap)


def _section_title(text: str) -> None:
    st.markdown(f"### {text}")


def _inject_css() -> None:
    """
    Clean, aligned layout: consistent widths, reduced blank gaps,
    tighter captions, and better alignment across the whole step.
    """
    st.markdown(
        """
        <style>
          /* Make widgets full-width consistently */
          div[data-testid="stTextInput"] input,
          div[data-testid="stTextArea"] textarea,
          div[data-testid="stNumberInput"] input,
          div[data-testid="stSelectbox"] div[role="combobox"],
          div[data-testid="stDateInput"] input {
            width: 100% !important;
          }

          /* Reduce random vertical gaps in this page */
          [data-testid="stVerticalBlock"] { gap: 0.70rem; }

          /* Captions tighter */
          .stCaption { margin-top: -6px; }

          /* Tabs spacing */
          button[data-baseweb="tab"] { padding: 8px 12px; }

          /* Form submit area spacing */
          div[data-testid="stForm"] { margin-top: 0.25rem; }

          /* Small screens: less side padding */
          @media (max-width: 700px){
            .block-container { padding-left: 1rem; padding-right: 1rem; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _init_state() -> None:
    ss = st.session_state
    ss.setdefault("general_info_overrides", {})
    ss.setdefault("general_info_date_formats", {})
    ss.setdefault("general_info_cost_currency", {})
    ss.setdefault("general_info_cost_amount", {})
    ss.setdefault("_t6_step2_saved", False)


def _get_default(field: str, ctx: Tool6Context) -> str:
    return _s((ctx.defaults or {}).get(field, ""))


def _get_value(field: str, ctx: Tool6Context) -> str:
    overrides = st.session_state.get("general_info_overrides", {})
    return _s(overrides.get(field, _get_default(field, ctx)))


def _show_hint(field: str, ctx: Tool6Context) -> None:
    hint = _s((ctx.hints or {}).get(field, ""))
    if hint:
        st.caption(hint)


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
# Widgets
# -----------------------------------------------------------------------------
def w_text(field: str, ctx: Tool6Context, *, placeholder: str = "", help_text: str = "") -> str:
    val = st.text_input(
        field,
        value=_get_value(field, ctx),
        placeholder=placeholder,
        key=_key(field, "text"),
        help=help_text or None,
    )
    _show_hint(field, ctx)
    return val


def w_select(field: str, ctx: Tool6Context, options: List[str], *, allow_empty: bool = True, help_text: str = "") -> str:
    cur = _get_value(field, ctx)
    opts = ([""] + options) if allow_empty else options
    idx = opts.index(cur) if cur in opts else 0

    val = st.selectbox(
        field,
        options=opts,
        index=idx,
        key=_key(field, "select"),
        help=help_text or None,
    )
    _show_hint(field, ctx)
    return _s(val)


def w_yes_no(field: str, ctx: Tool6Context, *, allow_empty: bool = True) -> str:
    return w_select(field, ctx, YES_NO, allow_empty=allow_empty)


def w_percent(field: str, ctx: Tool6Context) -> str:
    cur = _get_value(field, ctx)
    try:
        cur_f = float(cur) if _s(cur) else 0.0
    except Exception:
        cur_f = 0.0

    val = st.number_input(
        field,
        min_value=0.0,
        max_value=100.0,
        value=float(cur_f),
        step=1.0,
        key=_key(field, "percent"),
        help="Enter a value from 0 to 100.",
    )
    _show_hint(field, ctx)
    return f"{val:.0f}"


def w_email(field: str, ctx: Tool6Context, *, placeholder: str = "name@example.com") -> str:
    val = st.text_input(
        field,
        value=_get_value(field, ctx),
        placeholder=placeholder,
        key=_key(field, "email"),
        help="Please enter a valid email address.",
    )

    ok, msg = validate_email(val)
    if (not ok) and _s(val):
        st.error(f"Invalid email: {msg}")
    else:
        _show_hint(field, ctx)

    return val


def w_af_phone(field: str, ctx: Tool6Context) -> str:
    cur = _get_value(field, ctx)
    nine = _extract_af_9digits(cur)

    c1, c2 = st.columns([0.75, 2.25], gap="small")

    with c2:
        entered = st.text_input(
            field,
            value=nine,
            placeholder="9 digits (e.g., 701234567)",
            key=_key(field, "phone"),
            help="Enter 9 digits only. Leading 0 will be removed automatically.",
        )

    nine2 = _extract_af_9digits(entered)
    if nine2 and len(nine2) != 9:
        st.warning("Phone number must be exactly 9 digits after +93.")

    _show_hint(field, ctx)
    return f"+93{nine2}" if nine2 else ""


def w_date(field: str, ctx: Tool6Context) -> str:
    cover_label = _cover_date_format_label()
    per_field: Dict[str, str] = st.session_state["general_info_date_formats"]

    chosen_label = _s(per_field.get(field, cover_label))
    if chosen_label not in DATE_FORMATS:
        chosen_label = cover_label

    cur_raw = _get_value(field, ctx)
    cur_dt = _parse_date_guess(cur_raw) or date.today()

    c1, c2 = st.columns([2.2, 1.0], gap="small")
    with c1:
        picked = st.date_input(field, value=cur_dt, key=_key(field, "date"))
    with c2:
        chosen_label = st.selectbox(
            "Format",
            options=DATE_FORMAT_LABELS,
            index=DATE_FORMAT_LABELS.index(chosen_label),
            key=_key(field, "datefmt"),
            help="This format affects only this field (cover will not change).",
        )

    per_field[field] = chosen_label
    st.caption(f"Cover: {cover_label} • Field: {chosen_label}")
    _show_hint(field, ctx)

    return picked.strftime(DATE_FORMATS[chosen_label])


def w_money(field: str, ctx: Tool6Context) -> str:
    cur_override = _get_value(field, ctx)

    amt_state: Dict[str, float] = st.session_state["general_info_cost_amount"]
    cur_state: Dict[str, str] = st.session_state["general_info_cost_currency"]

    if field not in amt_state or field not in cur_state:
        m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]{3})\s*$", cur_override)
        if m:
            try:
                amt_state[field] = float(m.group(1))
            except Exception:
                amt_state[field] = 0.0
            cur_state[field] = m.group(2).upper()
        else:
            amt_state[field] = 0.0
            cur_state[field] = "AFN"

    cur_code = cur_state.get(field, "AFN")
    idx = CURRENCIES.index(cur_code) if cur_code in CURRENCIES else 0

    c1, c2 = st.columns([2.2, 1.0], gap="small")
    with c1:
        amount = st.number_input(
            field,
            min_value=0.0,
            value=float(amt_state.get(field, 0.0)),
            step=1.0,
            key=_key(field, "amount"),
            help="Enter the amount.",
        )
    with c2:
        cur = st.selectbox("Currency", options=CURRENCIES, index=idx, key=_key(field, "currency"))

    amt_state[field] = float(amount)
    cur_state[field] = _s(cur) or "AFN"
    _show_hint(field, ctx)

    if amount and amount > 0:
        amount_str = f"{amount:.2f}".rstrip("0").rstrip(".")
        return f"{amount_str} {cur_state[field]}"
    return ""


# -----------------------------------------------------------------------------
# Main render
# -----------------------------------------------------------------------------
def render_step(ctx: Tool6Context) -> bool:
    _init_state()
    _inject_css()

    ss = st.session_state

    # ✅ form prevents rerun on each keypress
    with st.form(_FORM_ID, clear_on_submit=False):
        updates: Dict[str, str] = {}

        tabs = st.tabs(["Project", "Respondent", "Monitoring", "Status / Other"])

        # -------------------- Project --------------------
        with tabs[0]:
            _section_title("Project Details")

            left, right = _cols2()
            with left:
                updates["Province"] = w_text("Province", ctx)
                updates["District"] = w_text("District", ctx)
                updates["Village / Community"] = w_text("Village / Community", ctx)
                updates["GPS points"] = w_text("GPS points", ctx, placeholder="e.g., 34.555, 69.207")
                updates["Project Name"] = w_text("Project Name", ctx)

            with right:
                updates["Date of Visit"] = w_date("Date of Visit", ctx)
                updates["Estimated Project Cost"] = w_money("Estimated Project Cost", ctx)
                updates["Contracted Project Cost"] = w_money("Contracted Project Cost", ctx)
                updates["Project Status"] = w_select("Project Status", ctx, ["Ongoing", "Completed", "Suspended"], allow_empty=True)
                updates["Project progress"] = w_select("Project progress", ctx, ["Ahead of Schedule", "On Schedule", "Running behind"], allow_empty=True)

            st.divider()

            _section_title("Contract & Progress")

            c1, c2 = _cols2()
            with c1:
                updates["Contract Start Date"] = w_date("Contract Start Date", ctx)
            with c2:
                updates["Contract End Date"] = w_date("Contract End Date", ctx)

            c3, c4 = _cols2()
            with c3:
                updates["Previous Physical Progress (%)"] = w_percent("Previous Physical Progress (%)", ctx)
            with c4:
                updates["Current Physical Progress (%)"] = w_percent("Current Physical Progress (%)", ctx)

        # -------------------- Respondent --------------------
        with tabs[1]:
            _section_title("Respondent / Participant")

            updates["Name of the respondent (Participant / UNICEF / IPs)"] = w_text(
                "Name of the respondent (Participant / UNICEF / IPs)", ctx
            )

            c1, c2 = _cols2(gap="large")
            with c1:
                updates["Sex of Respondent"] = w_select("Sex of Respondent", ctx, ["Male", "Female"], allow_empty=True)
                updates["Contact Number of the Respondent"] = w_af_phone("Contact Number of the Respondent", ctx)
            with c2:
                updates["Email Address of the Respondent"] = w_email("Email Address of the Respondent", ctx)

        # -------------------- Monitoring --------------------
        with tabs[2]:
            _section_title("Monitoring & Reporting")

            left, right = _cols2()
            with left:
                updates["Name of the IP, Organization / NGO"] = w_text("Name of the IP, Organization / NGO", ctx)
                updates["Name of the monitor engineer"] = w_text("Name of the monitor engineer", ctx)
                updates["Email of the monitor engineer"] = w_email("Email of the monitor engineer", ctx)

            with right:
                updates["Monitoring Report Number"] = w_text("Monitoring Report Number", ctx)
                updates["Date of Current Report"] = w_date("Date of Current Report", ctx)
                updates["Date of Last Monitoring Report"] = w_date("Date of Last Monitoring Report", ctx)
                updates["Number of Sites Visited"] = w_text("Number of Sites Visited", ctx, placeholder="e.g., 3")

        # -------------------- Status / Other --------------------
        with tabs[3]:
            _section_title("Status / Risk / Other")

            left, right = _cols2()
            with left:
                updates["Reason for delay"] = w_text("Reason for delay", ctx)
                updates["CDC Code"] = w_text("CDC Code", ctx)
                updates["Donor Name"] = w_text("Donor Name", ctx)

            with right:
                updates["Community agreement (Is the community/user group agreed on the well site?)"] = w_yes_no(
                    "Community agreement (Is the community/user group agreed on the well site?)", ctx, allow_empty=True
                )
                updates["Work safety considered"] = w_yes_no("Work safety considered", ctx, allow_empty=True)
                updates["Environmental risk"] = w_yes_no("Environmental risk", ctx, allow_empty=True)

            st.divider()

            _section_title("Available documents on site")

            d1, d2 = _cols2()
            docs_left = ["Contract", "Journal", "BOQ", "Design drawings"]
            docs_right = ["Site engineer", "Geophysical tests", "Water quality tests", "Pump test results"]

            with d1:
                for f in docs_left:
                    updates[f] = w_yes_no(f, ctx, allow_empty=True)
            with d2:
                for f in docs_right:
                    updates[f] = w_yes_no(f, ctx, allow_empty=True)

        saved = st.form_submit_button("Save changes", use_container_width=True)

    card_close()

    # Save only on submit
    if saved:
        ss["general_info_overrides"].update({k: _s(v) for k, v in updates.items()})
        ss["_t6_step2_saved"] = True

    # ✅ single status card (no duplicates / no blank frames)
    if ss.get("_t6_step2_saved"):
        status_card("Information saved", "Edits are stored and will be used in the report.", level="success")
    else:
        status_card("Not saved yet", "Make edits and click **Save changes**.", level="info")

    return True
