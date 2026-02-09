# src/Tools/steps/step_6_executive_summary.py
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card


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
    MOBILE_BREAKPOINT_PX = 900  # under this width, stack columns for better mobile UX

    # Editor
    EDITOR_HEIGHT_DESKTOP = 360
    EDITOR_HEIGHT_MOBILE = 280

    # Default options
    DEFAULT_STYLE = "Standard"
    DEFAULT_TONE = "Neutral"
    DEFAULT_FORMAT = "Paragraphs"
    DEFAULT_INCLUDE_WORK = True

    # Templates (names only; actual settings in TEMPLATE_LIBRARY below)
    DEFAULT_TEMPLATE = "Standard TPM (Balanced)"

    # Translation targets
    TRANSLATE_TARGETS = ["English", "Persian/Dari"]


# =============================================================================
# Template library
# =============================================================================
TEMPLATE_LIBRARY: Dict[str, Dict[str, Any]] = {
    # Balanced, report-like (default)
    "Standard TPM (Balanced)": {
        "style": "Standard",
        "tone": "Neutral",
        "format": "Paragraphs",
        "include_work": True,
        "include_detected_issues": True,
    },
    # Short, executive, scanning-friendly
    "Executive Brief (Short + Bullets)": {
        "style": "Short",
        "tone": "Neutral",
        "format": "Bullets",
        "include_work": True,
        "include_detected_issues": True,
    },
    # Strong follow-up tone
    "Action Follow-up (Tasks + Accountability)": {
        "style": "Standard",
        "tone": "Action-oriented",
        "format": "Paragraphs",
        "include_work": True,
        "include_detected_issues": True,
    },
    # Formal, donor-facing
    "Donor/Stakeholder (Formal + Detailed)": {
        "style": "Detailed",
        "tone": "Formal",
        "format": "Paragraphs",
        "include_work": True,
        "include_detected_issues": True,
    },
    # Minimal issues mention (useful when issues not reliable)
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
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"t6.s6.{h}"


def _sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def _is_nonempty(v: Any) -> bool:
    return _s(v) not in ("", " ")


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

    if fmt == "Bullets":
        blocks = [b.strip() for b in t.split("\n\n") if b.strip()]
        for b in blocks:
            st.markdown(f"- {b}")
    else:
        blocks = [b.strip() for b in t.split("\n\n") if b.strip()]
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

    wp_sentence = ""
    if include_work_progress:
        wp_sentence = _work_progress_summary(st.session_state.get(SS_WORK, []))

    p1 = (
        f"{tp['p1_open']}"
        f"implementation, functionality, and compliance of the {proj_phrase} in {location}{date_phrase}. "
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
    """
    Looks for an available translator callable in a few common places.
    Return: fn(text:str, target:str)->str or None
    """
    # 1) injected in session_state (recommended)
    fn = st.session_state.get("tool6_translate_fn")
    if callable(fn):
        return fn

    # 2) if ctx provides a translator attribute (optional)
    for attr in ("translate", "translator", "translate_text"):
        maybe = getattr(ctx, attr, None)
        if callable(maybe):
            return maybe

    return None


def _translate_text(ctx: Tool6Context, text: str, target: str) -> Tuple[str, Optional[str]]:
    """
    One-click translate with safe fallback (no hard dependency).
    If no translator function is configured, returns original with a message.
    """
    t = _split_paragraphs(text)
    if not t:
        return "", None

    fn = _get_translate_callable(ctx)
    if not fn:
        return t, (
            "No translation engine is configured. "
            "To enable one-click translate, register a callable in st.session_state['tool6_translate_fn'] "
            "that accepts (text, target) and returns translated text."
        )

    try:
        out = fn(t, target)  # expected signature: (text, target) -> text
        out = _split_paragraphs(out)
        return out, None
    except Exception as e:
        return t, f"Translation failed: {e}"


# =============================================================================
# State init (fast fingerprint + robust)
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

        # ✅ include issue-driving fields (previously missing)
        _s(row.get("pipeline_installation_issue")),
        _s(row.get("leakage_observed")),
        _s(row.get("solar_panel_dust")),
        _s(row.get("community_training_conducted")),

        # Overrides
        _s(overrides.get("Province")),
        _s(overrides.get("District")),
        _s(overrides.get("Village / Community")),
        _s(overrides.get("Project Name")),
        _s(overrides.get("Date of Visit")),
        _s(overrides.get("Project Status")),
        _s(overrides.get("Project progress")),

        # Controls
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
            sig_parts.extend([
                _s(r.get("Activities")),
                _s(r.get("Planned")),
                _s(r.get("Achieved")),
                _s(r.get("Progress")),
            ])
        core.append(_sha1_text("|".join(sig_parts)))

    return _sha1_text("|".join(core))


def _apply_template(ctx: Tool6Context, template_name: str) -> None:
    """
    Applies a template by setting controls, selecting issues, regenerating, and resetting editor to auto.
    This is an explicit user action => safe to overwrite editor.
    """
    ss = st.session_state
    tpl = TEMPLATE_LIBRARY.get(template_name, TEMPLATE_LIBRARY[UIConfig.DEFAULT_TEMPLATE])

    ss[SS_EXEC_STYLE] = tpl.get("style", UIConfig.DEFAULT_STYLE)
    ss[SS_EXEC_TONE] = tpl.get("tone", UIConfig.DEFAULT_TONE)
    ss[SS_EXEC_FORMAT] = tpl.get("format", UIConfig.DEFAULT_FORMAT)
    ss[SS_EXEC_INCLUDE_WORK] = bool(tpl.get("include_work", UIConfig.DEFAULT_INCLUDE_WORK))

    row = ctx.row or {}
    overrides = ss.get(SS_GENERAL_OVERRIDES, {}) or {}
    detected = _detect_issue_labels(row, overrides)

    if bool(tpl.get("include_detected_issues", True)):
        ss[SS_EXEC_ISSUES_SELECTED] = detected
    else:
        ss[SS_EXEC_ISSUES_SELECTED] = []

    # Force regenerate and reset editor to auto
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

    # Default issues selection if empty
    detected = _detect_issue_labels(row, overrides)
    if not isinstance(ss.get(SS_EXEC_ISSUES_SELECTED), list) or ss.get(SS_EXEC_ISSUES_SELECTED) is None:
        ss[SS_EXEC_ISSUES_SELECTED] = detected
    if isinstance(ss.get(SS_EXEC_ISSUES_SELECTED), list) and not ss.get(SS_EXEC_ISSUES_SELECTED):
        # Keep empty if user intentionally cleared; do not auto-refill here.
        pass

    # Fingerprint
    h = _fingerprint_core(
        row=row,
        overrides=overrides,
        style=_s(ss.get(SS_EXEC_STYLE)),
        tone=_s(ss.get(SS_EXEC_TONE)),
        fmt=_s(ss.get(SS_EXEC_FORMAT)),
        include_work=bool(ss.get(SS_EXEC_INCLUDE_WORK)),
        issues_selected=ss.get(SS_EXEC_ISSUES_SELECTED, []) or [],
    )

    # Regenerate auto text if needed
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

        # Only overwrite editor if user is NOT dirty and NOT approved
        if (not bool(ss.get(SS_EXEC_DIRTY))) and (ss.get(SS_EXEC_APPROVED) is False):
            ss[SS_EXEC_TEXT] = auto_text


# =============================================================================
# Responsive CSS (mobile/laptop/monitor)
# =============================================================================
def _inject_responsive_css() -> None:
    st.markdown(
        f"""
<style>
.t6-s6-subtle {{
  opacity: 0.85;
  font-size: 0.92rem;
}}

.t6-s6-sticky {{
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255,255,255,0.75);
  backdrop-filter: blur(8px);
  padding: 0.6rem 0.75rem;
  border-radius: 14px;
  border: 1px solid rgba(0,0,0,0.06);
  margin-bottom: 0.75rem;
}}

@media (prefers-color-scheme: dark) {{
  .t6-s6-sticky {{
    background: rgba(10,10,10,0.55);
    border: 1px solid rgba(255,255,255,0.10);
  }}
}}

@media (max-width: {UIConfig.MOBILE_BREAKPOINT_PX}px) {{
  div[data-testid="column"] {{
    width: 100% !important;
    flex: 1 1 100% !important;
  }}
}}
</style>
""",
        unsafe_allow_html=True,
    )


# =============================================================================
# MAIN RENDER
# =============================================================================
def render_step(ctx: Tool6Context) -> bool:
    """
    Step 6: Executive Summary (Advanced + Responsive + Templates + One-click Translation)
    - Auto-generate using data + style/tone/format + issue selection + optional Step5 summary
    - Responsive layout for mobile/laptop/monitor
    - Editor + live preview (reduced scrolling)
    - Dirty-state prevents overwriting user edits
    - Approve locks the text
    - Template Library: one-click apply presets
    - One-click translate: pluggable translation engine hook
    - Stores final text into general_info_overrides["Executive Summary Text"]
    """
    _inject_responsive_css()
    _ensure_state(ctx)
    ss = st.session_state

    with st.container(border=True):


        # Sticky action bar
        st.markdown('<div class="t6-s6-sticky">', unsafe_allow_html=True)
        a1, a2, a3, a4, a5 = st.columns([1.25, 1.25, 1.25, 1.4, 1.2], gap="small")

        with a1:
            if st.button("Regenerate", use_container_width=True, key=_key("regen")):
                ss[SS_EXEC_HASH] = ""
                ss[SS_EXEC_DIRTY] = False
                ss[SS_EXEC_APPROVED] = False
                _ensure_state(ctx)
                status_card("Regenerated", "Executive Summary regenerated from current inputs.", level="success")

        with a2:
            if st.button("Reset to Auto", use_container_width=True, key=_key("reset_auto")):
                ss[SS_EXEC_TEXT] = ss.get(SS_EXEC_AUTO, "")
                ss[SS_EXEC_DIRTY] = False
                ss[SS_EXEC_APPROVED] = False
                status_card("Reset", "Reverted to the latest auto-generated text.", level="success")

        with a3:
            if st.button("Show Auto Text", use_container_width=True, key=_key("show_auto")):
                st.code(ss.get(SS_EXEC_AUTO, ""), language="text")

        with a4:
            ss[SS_EXEC_SHOW_DIFF] = st.toggle(
                "Show Diff",
                value=bool(ss.get(SS_EXEC_SHOW_DIFF, False)),
                key=_key("show_diff"),
                help="Compare current edited text vs latest auto text.",
            )

        with a5:
            ss[SS_EXEC_APPROVED] = st.toggle(
                "Approved",
                value=bool(ss.get(SS_EXEC_APPROVED)),
                key=_key("approved"),
                help="When approved, this exact text is used in the report.",
            )
        st.markdown("</div>", unsafe_allow_html=True)

        # Tabs to reduce scrolling
        tab_draft, tab_insights, tab_controls = st.tabs(["Draft", "Insights", "Controls"])

        # -------------------------
        # DRAFT TAB (Editor + Preview)
        # -------------------------
        with tab_draft:
            left, right = st.columns([1.05, 0.95], gap="large")

            with left:
                st.markdown("**Editor**")
                st.caption("Edit freely. Blank lines separate paragraphs. Approve to lock the final text.")

                edited_raw = st.text_area(
                    "Executive Summary text",
                    value=ss.get(SS_EXEC_TEXT, ""),
                    height=UIConfig.EDITOR_HEIGHT_DESKTOP,
                    key=_key("editor"),
                    help="Keep paragraph spacing using blank lines. The report will keep this structure.",
                    label_visibility="visible",
                )

                edited = _split_paragraphs(edited_raw)

                # Dirty state: if edited differs from auto draft -> dirty
                if edited != _split_paragraphs(ss.get(SS_EXEC_AUTO, "")):
                    ss[SS_EXEC_DIRTY] = True
                else:
                    ss[SS_EXEC_DIRTY] = False

                ss[SS_EXEC_TEXT] = edited

                words = len([w for w in re.split(r"\s+", edited) if w.strip()]) if edited else 0
                chars = len(edited) if edited else 0
                st.markdown(f"<div class='t6-s6-subtle'>Words: {words} · Characters: {chars}</div>", unsafe_allow_html=True)

                if ss.get(SS_EXEC_SHOW_DIFF):
                    diff_txt = _simple_diff(ss.get(SS_EXEC_AUTO, ""), edited)
                    st.code(diff_txt, language="text")

            with right:
                st.markdown("**Live Preview (Report-like)**")
                st.caption("This preview shows how the text will read in the report.")
                with st.container(border=True):
                    _render_preview(ss.get(SS_EXEC_TEXT, ""), fmt=_s(ss.get(SS_EXEC_FORMAT)))

                if ss.get(SS_EXEC_APPROVED):
                    status_card("Approved", "This exact text will be used in the generated DOCX.", level="success")
                else:
                    if ss.get(SS_EXEC_DIRTY):
                        status_card("Edited (not approved)", "You edited the text. Approve when it’s final.", level="warning")
                    else:
                        status_card("Auto draft", "This matches the latest auto-generated version.", level="info")

        # -------------------------
        # INSIGHTS TAB
        # -------------------------
        with tab_insights:
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

            k1, k2, k3, k4 = st.columns([1.25, 1.25, 1.25, 1.25], gap="small")
            k1.metric("Province", province or "—")
            k2.metric("District", district or "—")
            k3.metric("Visit date", visit_date or "—")
            k4.metric("Project progress", progress_raw or "—")

            st.divider()

            st.markdown("**Detected issues (from survey fields)**")
            detected = _detect_issue_labels(row, overrides)
            if detected:
                for x in detected:
                    st.markdown(f"- {x}")
            else:
                st.info("No issues detected from available fields (or fields are empty).")

            if bool(ss.get(SS_EXEC_INCLUDE_WORK)):
                st.divider()
                st.markdown("**Work Progress Summary (Step 5)**")
                wp = _work_progress_summary(st.session_state.get(SS_WORK, []))
                if wp:
                    st.success(wp)
                else:
                    st.info("No Step 5 work progress rows found (or they are empty).")

            st.divider()
            st.markdown("**Snapshot**")
            s1, s2 = st.columns([1.5, 1.5], gap="small")
            with s1:
                st.write(f"Location: {loc or '—'}")
                st.write(f"Project: {project_name or '—'}")
            with s2:
                st.write(f"Status: {status_raw or '—'}")
                st.write(f"Approved: {'Yes' if ss.get(SS_EXEC_APPROVED) else 'No'}")

        # -------------------------
        # CONTROLS TAB (Templates + Style + Issues + Translation)
        # -------------------------
        with tab_controls:
            t1, t2, t3 = st.columns([2.2, 1.0, 1.0], gap="small")

            with t1:
                tpl_name = st.selectbox(
                    "Choose a template",
                    options=list(TEMPLATE_LIBRARY.keys()),
                    index=list(TEMPLATE_LIBRARY.keys()).index(_s(ss.get(SS_EXEC_TEMPLATE)) or UIConfig.DEFAULT_TEMPLATE),
                    key=_key("tpl_name"),
                    help="Templates set style/tone/format + issue inclusion rules. You can still customize after applying.",
                )
                ss[SS_EXEC_TEMPLATE] = tpl_name

            with t2:
                if st.button("Apply Template", use_container_width=True, key=_key("tpl_apply")):
                    _apply_template(ctx, ss[SS_EXEC_TEMPLATE])
                    _ensure_state(ctx)
                    # Explicit apply => set editor to auto (template result)
                    ss[SS_EXEC_TEXT] = ss.get(SS_EXEC_AUTO, "")
                    status_card("Template applied", "Draft updated using the selected template.", level="success")

            with t3:
                with st.popover("Template details", use_container_width=True):
                    tpl = TEMPLATE_LIBRARY.get(ss[SS_EXEC_TEMPLATE], {})
                    st.write(f"Style: {tpl.get('style')}")
                    st.write(f"Tone: {tpl.get('tone')}")
                    st.write(f"Format: {tpl.get('format')}")
                    st.write(f"Include Step 5: {'Yes' if tpl.get('include_work') else 'No'}")
                    st.write(f"Include issues: {'Yes' if tpl.get('include_detected_issues') else 'No'}")

            st.divider()

            # ---- Fine controls ----
            c1, c2, c3 = st.columns([1.2, 1.2, 1.2], gap="small")

            with c1:
                style = st.selectbox(
                    "Style",
                    options=["Short", "Standard", "Detailed"],
                    index=["Short", "Standard", "Detailed"].index(_s(ss.get(SS_EXEC_STYLE)) or UIConfig.DEFAULT_STYLE),
                    key=_key("style"),
                )
                ss[SS_EXEC_STYLE] = style

            with c2:
                tone = st.selectbox(
                    "Tone",
                    options=["Neutral", "Formal", "Action-oriented"],
                    index=["Neutral", "Formal", "Action-oriented"].index(_s(ss.get(SS_EXEC_TONE)) or UIConfig.DEFAULT_TONE),
                    key=_key("tone"),
                )
                ss[SS_EXEC_TONE] = tone

            with c3:
                fmt = st.selectbox(
                    "Output format",
                    options=["Paragraphs", "Bullets"],
                    index=["Paragraphs", "Bullets"].index(_s(ss.get(SS_EXEC_FORMAT)) or UIConfig.DEFAULT_FORMAT),
                    key=_key("format"),
                )
                ss[SS_EXEC_FORMAT] = fmt

            row = ctx.row or {}
            overrides = ss.get(SS_GENERAL_OVERRIDES, {}) or {}
            detected = _detect_issue_labels(row, overrides)
            selected = ss.get(SS_EXEC_ISSUES_SELECTED, []) or []

            s1, s2 = st.columns([2.2, 1.0], gap="small")
            with s1:
                ss[SS_EXEC_ISSUES_SELECTED] = st.multiselect(
                    "Include issues in the auto text",
                    options=sorted(list(set(detected + selected))),
                    default=selected,
                    key=_key("issues_sel"),
                    help="Select which issues should be explicitly mentioned in the executive summary.",
                )
            with s2:
                ss[SS_EXEC_INCLUDE_WORK] = st.toggle(
                    "Include Step 5 summary",
                    value=bool(ss.get(SS_EXEC_INCLUDE_WORK, UIConfig.DEFAULT_INCLUDE_WORK)),
                    key=_key("include_work"),
                )

            u1, u2 = st.columns([1.3, 1.0], gap="small")
            with u1:
                if st.button("Update Auto Draft (apply controls)", use_container_width=True, key=_key("apply_controls")):
                    ss[SS_EXEC_HASH] = ""
                    _ensure_state(ctx)
                    status_card("Updated", "Auto draft refreshed using the latest controls.", level="success")

            with u2:
                with st.expander("Preview auto text", expanded=False):
                    st.code(ss.get(SS_EXEC_AUTO, ""), language="text")

            st.divider()

            tr1, tr2, tr3, tr4 = st.columns([1.2, 1.2, 1.4, 1.2], gap="small")

            with tr1:
                ss[SS_EXEC_TRANSLATE_SOURCE] = st.selectbox(
                    "Translate source",
                    options=["Edited", "Auto"],
                    index=["Edited", "Auto"].index(_s(ss.get(SS_EXEC_TRANSLATE_SOURCE)) or "Edited"),
                    key=_key("tr_source"),
                )

            with tr2:
                ss[SS_EXEC_TRANSLATE_TARGET] = st.selectbox(
                    "Target language",
                    options=UIConfig.TRANSLATE_TARGETS,
                    index=UIConfig.TRANSLATE_TARGETS.index(_s(ss.get(SS_EXEC_TRANSLATE_TARGET)) or "Persian/Dari"),
                    key=_key("tr_target"),
                )

            with tr3:
                if st.button("Translate Now", use_container_width=True, key=_key("tr_now")):
                    source_text = ss.get(SS_EXEC_TEXT, "") if ss[SS_EXEC_TRANSLATE_SOURCE] == "Edited" else ss.get(SS_EXEC_AUTO, "")
                    translated, warn = _translate_text(ctx, source_text, ss[SS_EXEC_TRANSLATE_TARGET])

                    if warn:
                        status_card("Translation not configured", warn, level="warning")
                    else:
                        # Apply translated into editor (explicit user action)
                        ss[SS_EXEC_TEXT] = translated
                        ss[SS_EXEC_DIRTY] = True
                        ss[SS_EXEC_APPROVED] = False

                        # Store translated version separately for bilingual reports
                        gi = ss.get(SS_GENERAL_OVERRIDES, {}) or {}
                        gi[f"Executive Summary Text ({ss[SS_EXEC_TRANSLATE_TARGET]})"] = translated
                        ss[SS_GENERAL_OVERRIDES] = gi

                        status_card("Translated", "Translation applied to the editor and saved as a bilingual variant.", level="success")

            with tr4:
                with st.popover("How to enable", use_container_width=True):
                    st.write(
                        "To enable translation, provide a callable in:\n"
                        "st.session_state['tool6_translate_fn']\n\n"
                        "Signature:\n"
                        "def translate_fn(text: str, target: str) -> str\n\n"
                        "Then this button will translate instantly."
                    )

        # -------------------------
        # Final save + validation (always)
        # -------------------------
        edited_final = _split_paragraphs(ss.get(SS_EXEC_TEXT, ""))
        ss[SS_EXEC_TEXT] = edited_final

        if not edited_final:
            status_card("Empty text", "Executive Summary is empty. Please regenerate, apply a template, or write your text.", level="warning")
            card_close()
            return False

        # Save to overrides for report builder (primary)
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

        card_close()

    return True
