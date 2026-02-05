# src/Tools/steps/step_6_executive_summary.py
from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Any, Dict, Optional

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


# =============================================================================
# Generator (matches report section logic, plain text)
# =============================================================================
def _build_exec_summary_text(row: Dict[str, Any], overrides: Dict[str, Any]) -> str:
    row = row or {}
    overrides = overrides or {}

    province = _s(_pick_first_nonempty(row, overrides, ["A01_Province", "province", "Province"]))
    district = _s(_pick_first_nonempty(row, overrides, ["A02_District", "district", "District"]))
    village = _s(_pick_first_nonempty(row, overrides, ["Village", "village", "Community"]))
    project_name = _s(_pick_first_nonempty(row, overrides, ["Activity_Name", "project", "Project_Name"]))

    visit_date = _date_only_isoish(_pick_first_nonempty(row, overrides, ["starttime", "visit_date", "Date_of_Visit"]))

    status_raw = _norm_phrase(_pick_first_nonempty(row, overrides, ["Project_Status", "project_status", "status"]))
    progress_raw = _norm_phrase(_pick_first_nonempty(row, overrides, ["Project_progress", "project_progress", "progress"]))

    pipeline_issue = _pick_first_nonempty(row, overrides, ["pipeline_installation_issue", "pipeline_issue"])
    leakage = _pick_first_nonempty(row, overrides, ["leakage_observed", "leakage"])
    dust_panels = _pick_first_nonempty(row, overrides, ["solar_panel_dust", "dust_panels"])
    training = _pick_first_nonempty(row, overrides, ["community_training_conducted", "training_conducted"])

    location = _build_location_phrase(village, district, province) or "the monitored location"
    proj_phrase = (
        f"the Solar Water Supply project with household connections ({project_name})"
        if project_name
        else "the Solar Water Supply project with household connections"
    )
    date_phrase = f" on {visit_date}" if visit_date else ""

    p1 = (
        "This Third-Party Monitoring (TPM) field visit was conducted to assess the technical "
        f"implementation, functionality, and compliance of {proj_phrase} in {location}{date_phrase}. "
        "The visit focused on verifying system operational status, adherence to approved designs "
        "and Bill of Quantities (BoQ), and identifying any technical or operational risks that may "
        "affect long-term system performance."
    )

    bits = []
    if status_raw:
        bits.append(f"Project status was reported as {status_raw}.")
    if progress_raw:
        bits.append(f"Overall progress was reported as {progress_raw}.")
    p1_1 = " ".join(bits).strip()

    p2 = (
        "The assessment confirmed that the water supply system infrastructure—including bore wells, "
        "solar-powered pumping system, reservoirs, boundary wall, guard room, latrine, and stand taps—"
        "has been constructed and is currently operational. The system is supplying water to the "
        "targeted community, and the majority of stand taps were observed to be functional at the "
        "time of the visit."
    )

    issues = []
    if _as_yes(pipeline_issue):
        issues.append("pipeline installation and protection deficiencies")
    if _as_yes(leakage):
        issues.append("localized leakages in the distribution network")
    if _as_yes(dust_panels):
        issues.append("reduced solar panel efficiency due to dust accumulation")
    if _as_no(training):
        issues.append("lack of formal community training on system operation and maintenance")

    if issues:
        p3 = (
            "However, several technical and operational gaps were identified during the monitoring. "
            "These include " + ", ".join(issues) +
            ". While minor construction defects were observed in selected concrete works, no critical "
            "structural failures were noted during the visit."
        )
    else:
        p3 = (
            "No major technical or operational deficiencies were identified during the monitoring, "
            "and the system generally complies with the approved technical specifications."
        )

    p4 = (
        "Overall, the project is functional and delivering water services to the beneficiary community. "
        "Addressing the identified gaps through timely corrective actions and strengthening community "
        "capacity will further enhance system reliability, operational safety, and long-term "
        "sustainability of the water supply service."
    )

    parts = [p1]
    if p1_1:
        parts.append(p1_1)
    parts.extend([p2, p3, p4])

    return "\n\n".join([_s(x) for x in parts if _s(x)])


# =============================================================================
# State init (fast fingerprint)
# =============================================================================
def _ensure_state(ctx: Tool6Context) -> None:
    ss = st.session_state
    ss.setdefault(SS_EXEC_TEXT, "")
    ss.setdefault(SS_EXEC_AUTO, "")
    ss.setdefault(SS_EXEC_HASH, "")
    ss.setdefault(SS_EXEC_APPROVED, False)

    row = ctx.row or {}
    overrides = ss.get("general_info_overrides", {}) or {}

    # ✅ FAST fingerprint: only fields we actually use
    core = (
        _s(row.get("A01_Province")),
        _s(row.get("A02_District")),
        _s(row.get("Village")),
        _s(row.get("Activity_Name")),
        _s(row.get("starttime")),
        _s(row.get("Project_Status")),
        _s(row.get("Project_progress")),
        _s(overrides.get("Province")),
        _s(overrides.get("District")),
        _s(overrides.get("Village / Community")),
        _s(overrides.get("Project Name")),
        _s(overrides.get("Date of Visit")),
        _s(overrides.get("Project Status")),
        _s(overrides.get("Project progress")),
    )

    h = _sha1_text("|".join(core))

    if ss.get(SS_EXEC_HASH) != h:
        auto_text = _build_exec_summary_text(row, overrides)
        ss[SS_EXEC_HASH] = h
        ss[SS_EXEC_AUTO] = auto_text

        # overwrite editor only if user hasn't approved OR hasn't typed
        if not _s(ss.get(SS_EXEC_TEXT)) or ss.get(SS_EXEC_APPROVED) is False:
            ss[SS_EXEC_TEXT] = auto_text
            ss[SS_EXEC_APPROVED] = False


# =============================================================================
# MAIN RENDER
# =============================================================================
def render_step(ctx: Tool6Context) -> bool:
    """
    Step 6: Executive Summary
    - auto-generate from row + general_info_overrides
    - allow edit
    - allow approve
    - store final into general_info_overrides["Executive Summary Text"]
    """
    _ensure_state(ctx)
    ss = st.session_state

    st.subheader("Step 6 — Executive Summary")

    with st.container(border=True):
        card_open(
            "Executive Summary (Auto + Editable)",
            subtitle=(
                "This text is generated automatically from your data. "
                "You can edit it or approve as-is. The approved version will be used in the DOCX."
            ),
            variant="lg-variant-cyan",
        )

        c1, c2, c3 = st.columns([1, 1, 1], gap="small")

        with c1:
            if st.button("Regenerate from data", use_container_width=True, key=_key("regen")):
                ss[SS_EXEC_HASH] = ""
                _ensure_state(ctx)
                status_card("Regenerated", "Executive Summary regenerated from current inputs.", level="success")

        with c2:
            if st.button("Reset to last auto text", use_container_width=True, key=_key("reset_auto")):
                ss[SS_EXEC_TEXT] = ss.get(SS_EXEC_AUTO, "")
                ss[SS_EXEC_APPROVED] = False
                status_card("Reset", "Reverted to the latest auto-generated text.", level="success")

        with c3:
            ss[SS_EXEC_APPROVED] = st.toggle(
                "Approved",
                value=bool(ss.get(SS_EXEC_APPROVED)),
                key=_key("approved"),
                help="When approved, this exact text is used in the report.",
            )

        st.divider()

        edited = st.text_area(
            "Executive Summary text",
            value=ss.get(SS_EXEC_TEXT, ""),
            height=340,
            key=_key("editor"),
            help="Use blank lines to separate paragraphs. The report will keep this structure.",
        )

        edited = _split_paragraphs(edited)
        ss[SS_EXEC_TEXT] = edited

        if not edited:
            status_card("Empty text", "Executive Summary text is empty. Please regenerate or write your text.", level="warning")
            card_close()
            return False

        # Save to overrides (used by report_builder section)
        gi = ss.get("general_info_overrides", {}) or {}
        gi["Executive Summary Text"] = edited
        ss["general_info_overrides"] = gi

        st.divider()

        if ss.get(SS_EXEC_APPROVED):
            status_card("Approved", "This exact text will be used in the generated DOCX.", level="success")
        else:
            status_card("Not approved", "You can still proceed, but consider approving to lock the final text.", level="warning")

        card_close()

    return True
