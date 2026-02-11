# src/Tools/steps/step_6_executive_summary.py
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import status_card


# =============================================================================
# Session keys (Tool6 naming)
# =============================================================================
SS_EXEC_TEXT = "tool6_exec_summary_text"          # final text (editable)
SS_EXEC_APPROVED = "tool6_exec_summary_approved"  # bool
SS_EXEC_HASH = "tool6_exec_summary_hash"          # cache hash for auto-generation
SS_EXEC_AUTO = "tool6_exec_summary_auto_text"     # last generated auto text

# UX / Advanced automation
SS_EXEC_DIRTY = "tool6_exec_summary_dirty"        # user edited manually
SS_EXEC_STYLE = "tool6_exec_summary_style"        # "Short"|"Standard"|"Detailed"
SS_EXEC_TONE = "tool6_exec_summary_tone"          # "Neutral"|"Formal"|"Action-oriented"
SS_EXEC_FORMAT = "tool6_exec_summary_format"      # "Paragraphs"|"Bullets"
SS_EXEC_INCLUDE_WORK = "tool6_exec_summary_include_workprogress"  # bool
SS_EXEC_ISSUES_SELECTED = "tool6_exec_summary_issues_selected"    # list[str]
SS_EXEC_SHOW_DIFF = "tool6_exec_summary_show_diff"               # bool

# Template library + translation
SS_EXEC_TEMPLATE = "tool6_exec_summary_template"                 # selected template name
SS_EXEC_TRANSLATE_TARGET = "tool6_exec_summary_translate_target" # "English"|"Persian/Dari"
SS_EXEC_TRANSLATE_SOURCE = "tool6_exec_summary_translate_source" # "Edited"|"Auto"

# Upstream keys
SS_GENERAL_OVERRIDES = "general_info_overrides"
SS_WORK = "tool6_work_progress_rows"  # Step 5 output (optional)


# =============================================================================
# Config
# =============================================================================
class UIConfig:
    # Responsive behavior
    MOBILE_BREAKPOINT_PX = 900

    # Editor
    EDITOR_HEIGHT_DESKTOP = 360
    EDITOR_HEIGHT_MOBILE = 280

    # Default options
    DEFAULT_STYLE = "Standard"
    DEFAULT_TONE = "Neutral"
    DEFAULT_FORMAT = "Paragraphs"
    DEFAULT_INCLUDE_WORK = True

    # Templates
    DEFAULT_TEMPLATE = "Standard TPM (Balanced)"

    # Translation targets
    TRANSLATE_TARGETS = ["English", "Persian/Dari"]

    # Layout
    MAX_CONTENT_WIDTH_PX = 1180


# =============================================================================
# Template library
# =============================================================================
TEMPLATE_LIBRARY: Dict[str, Dict[str, Any]] = {
    "Standard TPM (Balanced)": {
        "style": "Standard",
        "tone": "Neutral",
        "format": "Paragraphs",
        "include_work": True,
        "include_detected_issues": True,
    },
    "Executive Brief (Short + Bullets)": {
        "style": "Short",
        "tone": "Neutral",
        "format": "Bullets",
        "include_work": True,
        "include_detected_issues": True,
    },
    "Action Follow-up (Tasks + Accountability)": {
        "style": "Standard",
        "tone": "Action-oriented",
        "format": "Paragraphs",
        "include_work": True,
        "include_detected_issues": True,
    },
    "Donor/Stakeholder (Formal + Detailed)": {
        "style": "Detailed",
        "tone": "Formal",
        "format": "Paragraphs",
        "include_work": True,
        "include_detected_issues": True,
    },
    "Clean Summary (No Issues Mentioned)": {
        "style": "Standard",
        "tone": "Neutral",
        "format": "Paragraphs",
        "include_work": True,
        "include_detected_issues": False,
    },
}


# =============================================================================
# Small utils
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()
    return f"t6.s6.{h}"


def _sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def _is_nonempty(v: Any) -> bool:
    return _s(v) not in ("", " ")


def _safe_index(options: List[str], value: str, default_value: str) -> int:
    """
    Streamlit selectbox index must be valid. This helper prevents ValueError
    and keeps sections aligned (no broken widgets -> no layout shift).
    """
    v = value if value in options else default_value
    try:
        return options.index(v)
    except Exception:
        return 0


def _pick_first_nonempty(row: Dict[str, Any], overrides: Dict[str, Any], keys) -> Any:
    keys_list = [keys] if isinstance(keys, str) else list(keys)
    for k in keys_list:
        if k in overrides and _is_nonempty(overrides.get(k)):
            return overrides.get(k)
    for k in keys_list:
        if _is_nonempty(row.get(k)):
            return row.get(k)
    return None


def _parse_bool_like(v: Any) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        iv = int(v)
        if iv == 1:
            return True
        if iv == 0:
            return False
    sv = _s(v).lower()
    if sv in {"yes", "y", "true", "1", "checked", "✔", "✅"}:
        return True
    if sv in {"no", "n", "false", "0", "unchecked", "✘", "❌"}:
        return False
    return None


def _as_yes(v: Any) -> bool:
    return _parse_bool_like(v) is True


def _as_no(v: Any) -> bool:
    return _parse_bool_like(v) is False


def _norm_phrase(v: Any) -> str:
    sv = _s(v)
    if not sv:
        return ""
    sv = " ".join(sv.split())
    return sv.rstrip(" .;:,")


def _date_only_isoish(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()

    sv = _s(v)
    if not sv:
        return ""

    sv_clean = sv.strip().replace("T", " ").replace("Z", "")
    if "." in sv_clean:
        sv_clean = sv_clean.split(".")[0].strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(sv_clean, fmt)
            return dt.date().isoformat()
        except Exception:
            pass

    return sv_clean.split(" ")[0].strip()


def _build_location_phrase(village: str, district: str, province: str) -> str:
    parts = [p for p in [_s(village), _s(district), _s(province)] if p]
    return ", ".join(parts)


def _split_paragraphs(text: str) -> str:
    t = (text or "").replace("\r\n", "\n")
    t = "\n".join([ln.rstrip() for ln in t.split("\n")])
    while "\n\n\n" in t:
        t = t.replace("\n\n\n", "\n\n")
    return t.strip()


def _render_preview(text: str, fmt: str) -> None:
    t = _split_paragraphs(text)
    if not t:
        st.info("Preview is empty.")
        return

    blocks = [b.strip() for b in t.split("\n\n") if b.strip()]
    if fmt == "Bullets":
        for b in blocks:
            st.markdown(f"- {b}")
    else:
        for b in blocks:
            st.markdown(b)
            st.write("")


def _simple_diff(a: str, b: str, max_lines: int = 120) -> str:
    a_lines = (a or "").splitlines()
    b_lines = (b or "").splitlines()

    out: List[str] = []
    out.append("Legend: - removed | + added |   unchanged")
    out.append("")

    i = 0
    j = 0
    while i < len(a_lines) and j < len(b_lines) and len(out) < max_lines:
        if a_lines[i] == b_lines[j]:
            out.append(f"  {a_lines[i]}")
            i += 1
            j += 1
        else:
            out.append(f"- {a_lines[i]}")
            out.append(f"+ {b_lines[j]}")
            i += 1
            j += 1

    while i < len(a_lines) and len(out) < max_lines:
        out.append(f"- {a_lines[i]}")
        i += 1
    while j < len(b_lines) and len(out) < max_lines:
        out.append(f"+ {b_lines[j]}")
        j += 1

    if len(out) >= max_lines:
        out.append("")
        out.append("… diff truncated …")

    return "\n".join(out)


# =============================================================================
# Work Progress (Step 5) summary (optional)
# =============================================================================
def _safe_float(v: Any) -> float:
    s = _s(v).replace(",", "").strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def _parse_progress_percent(progress_text: str) -> int:
    t = _s(progress_text)
    if not t:
        return 0
    t = t.replace("%", "").strip()
    try:
        n = int(float(t))
    except Exception:
        return 0
    return max(0, min(100, n))


def _work_progress_summary(rows: Any) -> str:
    if not isinstance(rows, list) or not rows:
        return ""

    acts = 0
    planned_sum = 0.0
    achieved_sum = 0.0
    prog_sum = 0
    prog_n = 0

    for r in rows:
        if not isinstance(r, dict):
            continue
        if _s(r.get("Activities")):
            acts += 1
        planned_sum += _safe_float(r.get("Planned"))
        achieved_sum += _safe_float(r.get("Achieved"))
        p = _parse_progress_percent(_s(r.get("Progress")))
        if p > 0 or _s(r.get("Progress")):
            prog_sum += p
            prog_n += 1

    if acts == 0:
        return ""

    avg_prog = int(round(prog_sum / prog_n)) if prog_n else 0
    return (
        f"During the visit, {acts} key activities were reviewed; aggregated planned versus achieved outputs "
        f"were {planned_sum:.0f} and {achieved_sum:.0f}, with an average reported progress of {avg_prog}%."
    )


# =============================================================================
# Issues detection + selection
# =============================================================================
def _detect_issue_labels(row: Dict[str, Any], overrides: Dict[str, Any]) -> List[str]:
    pipeline_issue = _pick_first_nonempty(row, overrides, ["pipeline_installation_issue", "pipeline_issue"])
    leakage = _pick_first_nonempty(row, overrides, ["leakage_observed", "leakage"])
    dust_panels = _pick_first_nonempty(row, overrides, ["solar_panel_dust", "dust_panels"])
    training = _pick_first_nonempty(row, overrides, ["community_training_conducted", "training_conducted"])

    issues: List[str] = []
    if _as_yes(pipeline_issue):
        issues.append("Pipeline installation/protection deficiencies")
    if _as_yes(leakage):
        issues.append("Localized leakages in the distribution network")
    if _as_yes(dust_panels):
        issues.append("Reduced solar panel efficiency due to dust accumulation")
    if _as_no(training):
        issues.append("Lack of formal community training on O&M")
    return issues


# =============================================================================
# Generator (advanced: style/tone/format + issue selection + work progress)
# =============================================================================
def _tone_phrases(tone: str) -> Dict[str, str]:
    tone = tone or UIConfig.DEFAULT_TONE
    if tone == "Formal":
        return {
            "p1_open": "This Third-Party Monitoring (TPM) field visit was conducted to assess the technical ",
            "p3_open": "However, several technical and operational gaps were identified during the monitoring. ",
            "p4_open": "Overall, the project is functional and delivering water services to the beneficiary community. ",
            "action_hint": "Timely corrective actions are recommended to mitigate risks and strengthen sustainability.",
        }
    if tone == "Action-oriented":
        return {
            "p1_open": "This TPM field visit assessed the technical implementation and functionality of the ",
            "p3_open": "Key gaps requiring immediate follow-up were identified: ",
            "p4_open": "The project is delivering water services; prioritize corrective actions to improve reliability and sustainability. ",
            "action_hint": "Follow up with corrective measures, assign responsibilities, and track completion.",
        }
    return {
        "p1_open": "This Third-Party Monitoring (TPM) field visit was conducted to assess the technical ",
        "p3_open": "However, several technical and operational gaps were identified during the monitoring. ",
        "p4_open": "Overall, the project is functional and delivering water services to the beneficiary community. ",
        "action_hint": "Addressing the identified gaps through timely corrective actions will further enhance system performance.",
    }


def _build_exec_summary_text_advanced(
    row: Dict[str, Any],
    overrides: Dict[str, Any],
    style: str,
    tone: str,
    fmt: str,
    issues_selected: List[str],
    include_work_progress: bool,
) -> str:
    row = row or {}
    overrides = overrides or {}

    province = _s(_pick_first_nonempty(row, overrides, ["A01_Province", "province", "Province"]))
    district = _s(_pick_first_nonempty(row, overrides, ["A02_District", "district", "District"]))
    village = _s(_pick_first_nonempty(row, overrides, ["Village", "village", "Community"]))
    project_name = _s(_pick_first_nonempty(row, overrides, ["Activity_Name", "project", "Project_Name"]))

    visit_date = _date_only_isoish(_pick_first_nonempty(row, overrides, ["starttime", "visit_date", "Date_of_Visit"]))
    status_raw = _norm_phrase(_pick_first_nonempty(row, overrides, ["Project_Status", "project_status", "status"]))
    progress_raw = _norm_phrase(_pick_first_nonempty(row, overrides, ["Project_progress", "project_progress", "progress"]))

    location = _build_location_phrase(village, district, province) or "the monitored location"
    proj_phrase = (
        f"Solar Water Supply project with household connections ({project_name})"
        if project_name
        else "Solar Water Supply project with household connections"
    )
    date_phrase = f" on {visit_date}" if visit_date else ""

    tp = _tone_phrases(tone)

    wp_sentence = _work_progress_summary(st.session_state.get(SS_WORK, [])) if include_work_progress else ""

    p1 = (
        f"{tp['p1_open']}implementation, functionality, and compliance of the {proj_phrase} in {location}{date_phrase}. "
        "The visit focused on verifying operational status, adherence to approved designs and BoQ, "
        "and identifying risks that may affect long-term system performance."
    )

    bits = []
    if status_raw:
        bits.append(f"Project status was reported as {status_raw}.")
    if progress_raw:
        bits.append(f"Overall progress was reported as {progress_raw}.")
    p_status = " ".join(bits).strip()

    if style == "Short":
        p2 = (
            "The water supply system infrastructure was observed to be constructed and operational, "
            "with water being supplied to the community and most stand taps functional."
        )
    elif style == "Detailed":
        p2 = (
            "The assessment confirmed that key infrastructure components—including bore wells, a solar-powered pumping system, "
            "reservoirs, a boundary wall, guard room, latrine, and stand taps—were in place. The system was supplying water "
            "to the target community, and the majority of stand taps were observed to be functional during the visit."
        )
    else:
        p2 = (
            "The assessment confirmed that the water supply system infrastructure has been constructed and is currently operational. "
            "The system is supplying water to the targeted community, and the majority of stand taps were observed to be functional "
            "at the time of the visit."
        )

    issues = [i for i in (issues_selected or []) if _s(i)]
    if issues:
        if tone == "Action-oriented":
            p3 = tp["p3_open"] + ", ".join(issues) + "."
        else:
            p3 = (
                f"{tp['p3_open']}"
                "These include " + ", ".join(issues) +
                ". While minor construction defects may be present in selected works, no critical structural failures were noted "
                "during the visit."
            )
    else:
        p3 = (
            "No major technical or operational deficiencies were identified during the monitoring, "
            "and the system generally complies with the approved technical specifications."
        )

    if style == "Short":
        p4 = f"{tp['p4_open']}{tp['action_hint']}"
    elif style == "Detailed":
        p4 = (
            f"{tp['p4_open']}"
            "Addressing the identified gaps through corrective actions, strengthening community capacity for operation and maintenance, "
            "and maintaining routine preventive checks (e.g., leak management and solar panel cleaning) will enhance reliability, safety, "
            "and the long-term sustainability of services. "
            f"{tp['action_hint']}"
        )
    else:
        p4 = (
            f"{tp['p4_open']}"
            "Addressing the identified gaps through timely corrective actions and strengthening community capacity will further enhance "
            "system reliability, operational safety, and sustainability of services."
        )

    parts: List[str] = [p1]
    if p_status:
        parts.append(p_status)
    if wp_sentence:
        parts.append(wp_sentence)
    parts.extend([p2, p3, p4])

    text = "\n\n".join([_s(x) for x in parts if _s(x)])
    text = _split_paragraphs(text)

    if fmt == "Bullets":
        bullets = [b.strip() for b in text.split("\n\n") if b.strip()]
        return "\n\n".join(bullets)
    return text


# =============================================================================
# Translation (pluggable: uses a callable if available)
# =============================================================================
def _get_translate_callable(ctx: Tool6Context):
    fn = st.session_state.get("tool6_translate_fn")
    if callable(fn):
        return fn
    for attr in ("translate", "translator", "translate_text"):
        maybe = getattr(ctx, attr, None)
        if callable(maybe):
            return maybe
    return None


def _translate_text(ctx: Tool6Context, text: str, target: str) -> Tuple[str, Optional[str]]:
    t = _split_paragraphs(text)
    if not t:
        return "", None

    fn = _get_translate_callable(ctx)
    if not fn:
        return t, (
            "No translation engine is configured. "
            "Register st.session_state['tool6_translate_fn'] = lambda text, target: ... "
            "(signature: (text:str, target:str) -> str)."
        )

    try:
        out = fn(t, target)
        out = _split_paragraphs(out)
        return out, None
    except Exception as e:
        return t, f"Translation failed: {e}"


# =============================================================================
# Fingerprint + state init (fast)
# =============================================================================
def _fingerprint_core(
    row: Dict[str, Any],
    overrides: Dict[str, Any],
    style: str,
    tone: str,
    fmt: str,
    include_work: bool,
    issues_selected: List[str],
) -> str:
    row = row or {}
    overrides = overrides or {}

    core = [
        _s(row.get("A01_Province")),
        _s(row.get("A02_District")),
        _s(row.get("Village")),
        _s(row.get("Activity_Name")),
        _s(row.get("starttime")),
        _s(row.get("Project_Status")),
        _s(row.get("Project_progress")),

        # issue-driving fields
        _s(row.get("pipeline_installation_issue")),
        _s(row.get("leakage_observed")),
        _s(row.get("solar_panel_dust")),
        _s(row.get("community_training_conducted")),

        # overrides (common human fields)
        _s(overrides.get("Province")),
        _s(overrides.get("District")),
        _s(overrides.get("Village / Community")),
        _s(overrides.get("Project Name")),
        _s(overrides.get("Date of Visit")),
        _s(overrides.get("Project Status")),
        _s(overrides.get("Project progress")),

        # controls
        _s(style),
        _s(tone),
        _s(fmt),
        "1" if include_work else "0",
        "|".join([_s(x) for x in (issues_selected or [])]),
    ]

    if include_work:
        work_rows = st.session_state.get(SS_WORK, []) or []
        sig_parts: List[str] = []
        for r in work_rows[:30]:
            if not isinstance(r, dict):
                continue
            sig_parts.extend([_s(r.get("Activities")), _s(r.get("Planned")), _s(r.get("Achieved")), _s(r.get("Progress"))])
        core.append(_sha1_text("|".join(sig_parts)))

    return _sha1_text("|".join(core))


def _apply_template(ctx: Tool6Context, template_name: str) -> None:
    ss = st.session_state
    tpl = TEMPLATE_LIBRARY.get(template_name, TEMPLATE_LIBRARY[UIConfig.DEFAULT_TEMPLATE])

    ss[SS_EXEC_STYLE] = tpl.get("style", UIConfig.DEFAULT_STYLE)
    ss[SS_EXEC_TONE] = tpl.get("tone", UIConfig.DEFAULT_TONE)
    ss[SS_EXEC_FORMAT] = tpl.get("format", UIConfig.DEFAULT_FORMAT)
    ss[SS_EXEC_INCLUDE_WORK] = bool(tpl.get("include_work", UIConfig.DEFAULT_INCLUDE_WORK))

    row = ctx.row or {}
    overrides = ss.get(SS_GENERAL_OVERRIDES, {}) or {}
    detected = _detect_issue_labels(row, overrides)

    ss[SS_EXEC_ISSUES_SELECTED] = detected if bool(tpl.get("include_detected_issues", True)) else []

    ss[SS_EXEC_HASH] = ""
    ss[SS_EXEC_DIRTY] = False
    ss[SS_EXEC_APPROVED] = False


def _ensure_state(ctx: Tool6Context) -> None:
    ss = st.session_state

    ss.setdefault(SS_EXEC_TEXT, "")
    ss.setdefault(SS_EXEC_AUTO, "")
    ss.setdefault(SS_EXEC_HASH, "")
    ss.setdefault(SS_EXEC_APPROVED, False)

    ss.setdefault(SS_EXEC_DIRTY, False)
    if not isinstance(ss[SS_EXEC_DIRTY], bool):
        ss[SS_EXEC_DIRTY] = False

    ss.setdefault(SS_EXEC_STYLE, UIConfig.DEFAULT_STYLE)
    ss.setdefault(SS_EXEC_TONE, UIConfig.DEFAULT_TONE)
    ss.setdefault(SS_EXEC_FORMAT, UIConfig.DEFAULT_FORMAT)
    ss.setdefault(SS_EXEC_INCLUDE_WORK, UIConfig.DEFAULT_INCLUDE_WORK)

    ss.setdefault(SS_EXEC_ISSUES_SELECTED, [])
    if not isinstance(ss.get(SS_EXEC_ISSUES_SELECTED), list):
        ss[SS_EXEC_ISSUES_SELECTED] = []

    ss.setdefault(SS_EXEC_SHOW_DIFF, False)

    ss.setdefault(SS_EXEC_TEMPLATE, UIConfig.DEFAULT_TEMPLATE)
    if ss[SS_EXEC_TEMPLATE] not in TEMPLATE_LIBRARY:
        ss[SS_EXEC_TEMPLATE] = UIConfig.DEFAULT_TEMPLATE

    ss.setdefault(SS_EXEC_TRANSLATE_TARGET, "Persian/Dari")
    if ss[SS_EXEC_TRANSLATE_TARGET] not in UIConfig.TRANSLATE_TARGETS:
        ss[SS_EXEC_TRANSLATE_TARGET] = "Persian/Dari"

    ss.setdefault(SS_EXEC_TRANSLATE_SOURCE, "Edited")
    if ss[SS_EXEC_TRANSLATE_SOURCE] not in ("Edited", "Auto"):
        ss[SS_EXEC_TRANSLATE_SOURCE] = "Edited"

    row = ctx.row or {}
    overrides = ss.get(SS_GENERAL_OVERRIDES, {}) or {}

    # default selection if first time only
    if ss.get(SS_EXEC_ISSUES_SELECTED) == [] and (SS_EXEC_HASH not in ss or not ss.get(SS_EXEC_HASH)):
        ss[SS_EXEC_ISSUES_SELECTED] = _detect_issue_labels(row, overrides)

    # fingerprint + regen only when changed
    h = _fingerprint_core(
        row=row,
        overrides=overrides,
        style=_s(ss.get(SS_EXEC_STYLE)),
        tone=_s(ss.get(SS_EXEC_TONE)),
        fmt=_s(ss.get(SS_EXEC_FORMAT)),
        include_work=bool(ss.get(SS_EXEC_INCLUDE_WORK)),
        issues_selected=ss.get(SS_EXEC_ISSUES_SELECTED, []) or [],
    )

    if ss.get(SS_EXEC_HASH) != h:
        auto_text = _build_exec_summary_text_advanced(
            row=row,
            overrides=overrides,
            style=_s(ss.get(SS_EXEC_STYLE)),
            tone=_s(ss.get(SS_EXEC_TONE)),
            fmt=_s(ss.get(SS_EXEC_FORMAT)),
            issues_selected=ss.get(SS_EXEC_ISSUES_SELECTED, []) or [],
            include_work_progress=bool(ss.get(SS_EXEC_INCLUDE_WORK)),
        )
        ss[SS_EXEC_HASH] = h
        ss[SS_EXEC_AUTO] = auto_text

        # don't clobber user's edits
        if (not bool(ss.get(SS_EXEC_DIRTY))) and (ss.get(SS_EXEC_APPROVED) is False):
            ss[SS_EXEC_TEXT] = auto_text


# =============================================================================
# UI: alignment + card system (fixes)
# =============================================================================
def _inject_ui_css() -> None:
    st.markdown(
        f"""
<style>
/* Center the whole step and keep consistent width */
.t6-s6-wrap {{
  max-width: {UIConfig.MAX_CONTENT_WIDTH_PX}px;
  margin-left: auto;
  margin-right: auto;
}}

/* Make Streamlit columns top-aligned and consistent */
div[data-testid="stHorizontalBlock"] {{
  align-items: stretch;
}}
div[data-testid="column"] {{
  display: flex;
  flex-direction: column;
  align-self: stretch;
}}

/* Responsive columns: stack on mobile */
@media (max-width: {UIConfig.MOBILE_BREAKPOINT_PX}px) {{
  div[data-testid="column"] {{
    width: 100% !important;
    flex: 1 1 100% !important;
  }}
  .t6-s6-sticky {{
    position: relative !important;
    top: unset !important;
  }}
}}

/* Sticky toolbar */
.t6-s6-sticky {{
  position: sticky;
  top: 0.25rem;
  z-index: 80;
  backdrop-filter: blur(8px);
  padding: 0.65rem 0.75rem;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.10);
  background: rgba(15,15,18,0.55);
  margin-bottom: 0.85rem;
}}

/* Card */
.t6-s6-card {{
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 14px;
  padding: 14px;
  background: rgba(255,255,255,0.02);
  margin-bottom: 12px;

  /* alignment: ensure full height in column */
  display: flex;
  flex-direction: column;
  gap: 8px;
}}
.t6-s6-title {{
  font-weight: 700;
  margin: 0;
}}
.t6-s6-subtle {{
  opacity: 0.85;
  font-size: 0.92rem;
}}
.t6-s6-row {{
  display:flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}}
.t6-s6-pill {{
  border: 1px solid rgba(255,255,255,0.14);
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.84rem;
  opacity: 0.9;
}}

/* Prevent markdown titles from adding extra top spacing inside cards */
.t6-s6-card .stMarkdown p {{
  margin-top: 0.2rem;
  margin-bottom: 0.2rem;
}}
</style>
""",
        unsafe_allow_html=True,
    )


def _card(title: str, body_fn, *, help_text: str = "") -> None:
    st.markdown("<div class='t6-s6-card'>", unsafe_allow_html=True)
    st.markdown(f"<div class='t6-s6-title'>{title}</div>", unsafe_allow_html=True)
    if help_text:
        st.caption(help_text)
    body_fn()
    st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# Fragments (speed): toolbar, editor, preview, controls
# =============================================================================
@st.fragment
def _sticky_bar(ctx: Tool6Context) -> None:
    ss = st.session_state

    st.markdown("<div class='t6-s6-sticky'>", unsafe_allow_html=True)
    a1, a2, a3, a4, a5 = st.columns([1.25, 1.25, 1.25, 1.4, 1.2], gap="small")

    with a1:
        if st.button("Regenerate", use_container_width=True, key=_key("regen")):
            ss[SS_EXEC_HASH] = ""
            ss[SS_EXEC_DIRTY] = False
            ss[SS_EXEC_APPROVED] = False
            _ensure_state(ctx)
            st.rerun()

    with a2:
        if st.button("Reset to Auto", use_container_width=True, key=_key("reset_auto")):
            ss[SS_EXEC_TEXT] = ss.get(SS_EXEC_AUTO, "")
            ss[SS_EXEC_DIRTY] = False
            ss[SS_EXEC_APPROVED] = False
            st.rerun()

    with a3:
        if st.button("Show Auto Text", use_container_width=True, key=_key("show_auto")):
            with st.popover("Auto text", use_container_width=True):
                st.code(ss.get(SS_EXEC_AUTO, ""), language="text")

    with a4:
        ss[SS_EXEC_SHOW_DIFF] = st.toggle(
            "Show Diff",
            value=bool(ss.get(SS_EXEC_SHOW_DIFF, False)),
            key=_key("show_diff"),
        )

    with a5:
        ss[SS_EXEC_APPROVED] = st.toggle(
            "Approved",
            value=bool(ss.get(SS_EXEC_APPROVED)),
            key=_key("approved"),
        )

    st.markdown("</div>", unsafe_allow_html=True)


@st.fragment
def _draft_tab(ctx: Tool6Context) -> None:
    ss = st.session_state

    left, right = st.columns([1.05, 0.95], gap="large")

    def _editor_body():
        # pick height based on viewport-ish hint (we don't truly know client width; keep stable)
        height = UIConfig.EDITOR_HEIGHT_DESKTOP
        if st.session_state.get("t6_is_mobile") is True:
            height = UIConfig.EDITOR_HEIGHT_MOBILE

        edited_raw = st.text_area(
            "Executive Summary text",
            value=ss.get(SS_EXEC_TEXT, ""),
            height=height,
            key=_key("editor"),
            help="Keep blank lines between paragraphs. The report preserves paragraph structure.",
        )
        edited = _split_paragraphs(edited_raw)
        ss[SS_EXEC_TEXT] = edited

        auto = _split_paragraphs(ss.get(SS_EXEC_AUTO, ""))
        ss[SS_EXEC_DIRTY] = (edited != auto)

        words = len([w for w in re.split(r"\s+", edited) if w.strip()]) if edited else 0
        chars = len(edited) if edited else 0
        st.markdown(f"<div class='t6-s6-subtle'>Words: {words} · Characters: {chars}</div>", unsafe_allow_html=True)

        if bool(ss.get(SS_EXEC_SHOW_DIFF)):
            st.divider()
            st.code(_simple_diff(ss.get(SS_EXEC_AUTO, ""), edited), language="text")

    def _preview_body():
        st.caption("This preview approximates the report reading flow.")
        _render_preview(ss.get(SS_EXEC_TEXT, ""), fmt=_s(ss.get(SS_EXEC_FORMAT)))

        st.divider()
        if ss.get(SS_EXEC_APPROVED):
            status_card("Approved", "This exact text will be used in the generated DOCX.", level="success")
        else:
            if ss.get(SS_EXEC_DIRTY):
                status_card("Edited (not approved)", "You edited the text. Approve when final.", level="warning")
            else:
                status_card("Auto draft", "This matches the latest auto-generated version.", level="info")

    with left:
        _card("Editor", _editor_body, help_text="Edit freely. Blank lines separate paragraphs.")
    with right:
        _card("Live Preview", _preview_body, help_text="Preview updates with your edits.")


@st.fragment
def _insights_tab(ctx: Tool6Context) -> None:
    ss = st.session_state
    row = ctx.row or {}
    overrides = ss.get(SS_GENERAL_OVERRIDES, {}) or {}

    province = _s(_pick_first_nonempty(row, overrides, ["A01_Province", "province", "Province"]))
    district = _s(_pick_first_nonempty(row, overrides, ["A02_District", "district", "District"]))
    village = _s(_pick_first_nonempty(row, overrides, ["Village", "village", "Community"]))
    project_name = _s(_pick_first_nonempty(row, overrides, ["Activity_Name", "project", "Project_Name"]))
    visit_date = _date_only_isoish(_pick_first_nonempty(row, overrides, ["starttime", "visit_date", "Date_of_Visit"]))
    status_raw = _norm_phrase(_pick_first_nonempty(row, overrides, ["Project_Status", "project_status", "status"]))
    progress_raw = _norm_phrase(_pick_first_nonempty(row, overrides, ["Project_progress", "project_progress", "progress"]))

    loc = _build_location_phrase(village, district, province)
    detected = _detect_issue_labels(row, overrides)

    def _kpis_body():
        k1, k2, k3, k4 = st.columns([1.25, 1.25, 1.25, 1.25], gap="small")
        k1.metric("Province", province or "—")
        k2.metric("District", district or "—")
        k3.metric("Visit date", visit_date or "—")
        k4.metric("Project progress", progress_raw or "—")

        st.markdown("<div class='t6-s6-row'>", unsafe_allow_html=True)
        st.markdown(f"<div class='t6-s6-pill'>Location: {loc or '—'}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='t6-s6-pill'>Project: {project_name or '—'}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='t6-s6-pill'>Status: {status_raw or '—'}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='t6-s6-pill'>Approved: {'Yes' if ss.get(SS_EXEC_APPROVED) else 'No'}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    def _issues_body():
        if detected:
            for x in detected:
                st.markdown(f"- {x}")
        else:
            st.info("No issues detected from available fields (or fields are empty).")

    def _work_body():
        if bool(ss.get(SS_EXEC_INCLUDE_WORK)):
            wp = _work_progress_summary(st.session_state.get(SS_WORK, []))
            if wp:
                st.success(wp)
            else:
                st.info("No Step 5 work progress rows found (or they are empty).")
        else:
            st.info("Step 5 summary is disabled in Controls.")

    _card("Snapshot", _kpis_body)
    _card("Detected issues", _issues_body)
    _card("Work progress (Step 5)", _work_body)


@st.fragment
def _controls_tab(ctx: Tool6Context) -> None:
    ss = st.session_state
    row = ctx.row or {}
    overrides = ss.get(SS_GENERAL_OVERRIDES, {}) or {}
    detected = _detect_issue_labels(row, overrides)

    def _tpl_body():
        opts = list(TEMPLATE_LIBRARY.keys())
        t1, t2, t3 = st.columns([2.2, 1.0, 1.0], gap="small")

        with t1:
            tpl_name = st.selectbox(
                "Choose a template",
                options=opts,
                index=_safe_index(opts, _s(ss.get(SS_EXEC_TEMPLATE)), UIConfig.DEFAULT_TEMPLATE),
                key=_key("tpl_name"),
            )
            ss[SS_EXEC_TEMPLATE] = tpl_name

        with t2:
            if st.button("Apply Template", use_container_width=True, key=_key("tpl_apply")):
                _apply_template(ctx, ss[SS_EXEC_TEMPLATE])
                _ensure_state(ctx)
                ss[SS_EXEC_TEXT] = ss.get(SS_EXEC_AUTO, "")
                st.rerun()

        with t3:
            with st.popover("Template details", use_container_width=True):
                tpl = TEMPLATE_LIBRARY.get(ss[SS_EXEC_TEMPLATE], {})
                st.write(f"Style: {tpl.get('style')}")
                st.write(f"Tone: {tpl.get('tone')}")
                st.write(f"Format: {tpl.get('format')}")
                st.write(f"Include Step 5: {'Yes' if tpl.get('include_work') else 'No'}")
                st.write(f"Include issues: {'Yes' if tpl.get('include_detected_issues') else 'No'}")

    def _controls_body():
        c1, c2, c3 = st.columns([1.2, 1.2, 1.2], gap="small")
        style_opts = ["Short", "Standard", "Detailed"]
        tone_opts = ["Neutral", "Formal", "Action-oriented"]
        fmt_opts = ["Paragraphs", "Bullets"]

        with c1:
            ss[SS_EXEC_STYLE] = st.selectbox(
                "Style",
                options=style_opts,
                index=_safe_index(style_opts, _s(ss.get(SS_EXEC_STYLE)), UIConfig.DEFAULT_STYLE),
                key=_key("style"),
            )
        with c2:
            ss[SS_EXEC_TONE] = st.selectbox(
                "Tone",
                options=tone_opts,
                index=_safe_index(tone_opts, _s(ss.get(SS_EXEC_TONE)), UIConfig.DEFAULT_TONE),
                key=_key("tone"),
            )
        with c3:
            ss[SS_EXEC_FORMAT] = st.selectbox(
                "Output format",
                options=fmt_opts,
                index=_safe_index(fmt_opts, _s(ss.get(SS_EXEC_FORMAT)), UIConfig.DEFAULT_FORMAT),
                key=_key("format"),
            )

        s1, s2 = st.columns([2.2, 1.0], gap="small")
        with s1:
            selected = ss.get(SS_EXEC_ISSUES_SELECTED, []) or []
            opts = sorted(list(set(detected + selected)))
            ss[SS_EXEC_ISSUES_SELECTED] = st.multiselect(
                "Include issues in auto text",
                options=opts,
                default=selected,
                key=_key("issues_sel"),
            )
        with s2:
            ss[SS_EXEC_INCLUDE_WORK] = st.toggle(
                "Include Step 5 summary",
                value=bool(ss.get(SS_EXEC_INCLUDE_WORK, UIConfig.DEFAULT_INCLUDE_WORK)),
                key=_key("include_work"),
            )

        # Apply -> regenerate only when user asks (fastest behavior)
        if st.button("Update Auto Draft (apply controls)", use_container_width=True, key=_key("apply_controls")):
            ss[SS_EXEC_HASH] = ""
            _ensure_state(ctx)
            st.rerun()

        with st.expander("Preview auto text", expanded=False):
            st.code(ss.get(SS_EXEC_AUTO, ""), language="text")

    def _translate_body():
        tr1, tr2, tr3, tr4 = st.columns([1.2, 1.2, 1.4, 1.2], gap="small")

        with tr1:
            src_opts = ["Edited", "Auto"]
            ss[SS_EXEC_TRANSLATE_SOURCE] = st.selectbox(
                "Translate source",
                options=src_opts,
                index=_safe_index(src_opts, _s(ss.get(SS_EXEC_TRANSLATE_SOURCE)), "Edited"),
                key=_key("tr_source"),
            )
        with tr2:
            tgt_opts = UIConfig.TRANSLATE_TARGETS
            ss[SS_EXEC_TRANSLATE_TARGET] = st.selectbox(
                "Target language",
                options=tgt_opts,
                index=_safe_index(tgt_opts, _s(ss.get(SS_EXEC_TRANSLATE_TARGET)), "Persian/Dari"),
                key=_key("tr_target"),
            )
        with tr3:
            if st.button("Translate Now", use_container_width=True, key=_key("tr_now")):
                source_text = ss.get(SS_EXEC_TEXT, "") if ss[SS_EXEC_TRANSLATE_SOURCE] == "Edited" else ss.get(SS_EXEC_AUTO, "")
                translated, warn = _translate_text(ctx, source_text, ss[SS_EXEC_TRANSLATE_TARGET])

                if warn:
                    status_card("Translation not configured", warn, level="warning")
                else:
                    ss[SS_EXEC_TEXT] = translated
                    ss[SS_EXEC_DIRTY] = True
                    ss[SS_EXEC_APPROVED] = False

                    gi = ss.get(SS_GENERAL_OVERRIDES, {}) or {}
                    gi[f"Executive Summary Text ({ss[SS_EXEC_TRANSLATE_TARGET]})"] = translated
                    ss[SS_GENERAL_OVERRIDES] = gi
                    st.rerun()

        with tr4:
            with st.popover("How to enable", use_container_width=True):
                st.write(
                    "Provide a callable in:\n"
                    "st.session_state['tool6_translate_fn']\n\n"
                    "Signature:\n"
                    "def translate_fn(text: str, target: str) -> str\n"
                )

    _card("Templates", _tpl_body)
    _card("Draft controls", _controls_body)
    _card("Translation", _translate_body)


# =============================================================================
# MAIN RENDER
# =============================================================================
def render_step(ctx: Tool6Context) -> bool:
    """
    Step 6: Executive Summary
    - generation only when fingerprint changes
    - card-based UI
    - fragments isolate rerenders (toolbar/editor/preview/controls)
    - never overwrite user edits unless explicit actions
    """
    _inject_ui_css()
    _ensure_state(ctx)
    ss = st.session_state

    # Center wrapper for consistent alignment across all sections/tabs
    st.markdown("<div class='t6-s6-wrap'>", unsafe_allow_html=True)

    with st.container(border=True):
        _sticky_bar(ctx)

        tab_draft, tab_insights, tab_controls = st.tabs(["Draft", "Insights", "Controls"])
        with tab_draft:
            _draft_tab(ctx)
        with tab_insights:
            _insights_tab(ctx)
        with tab_controls:
            _controls_tab(ctx)

        # Final save (always)
        edited_final = _split_paragraphs(ss.get(SS_EXEC_TEXT, ""))
        ss[SS_EXEC_TEXT] = edited_final

        if not edited_final:
            status_card(
                "Empty text",
                "Executive Summary is empty. Please regenerate, apply a template, or write your text.",
                level="warning",
            )
            st.markdown("</div>", unsafe_allow_html=True)
            return False

        # Save to overrides for report builder
        gi = ss.get(SS_GENERAL_OVERRIDES, {}) or {}
        gi["Executive Summary Text"] = edited_final
        ss[SS_GENERAL_OVERRIDES] = gi

        st.divider()
        if ss.get(SS_EXEC_APPROVED):
            status_card("Approved", "This exact text will be used in the generated DOCX.", level="success")
        else:
            if ss.get(SS_EXEC_DIRTY):
                status_card("Draft updated", "You edited/translated the text. Approve when final.", level="warning")
            else:
                status_card("Auto draft", "This matches the latest auto-generated version.", level="info")

    st.markdown("</div>", unsafe_allow_html=True)
    return True
