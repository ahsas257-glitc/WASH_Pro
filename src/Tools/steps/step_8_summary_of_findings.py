# src/Tools/steps/step_8_summary_of_findings.py
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Tuple, Optional

import streamlit as st

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None  # type: ignore

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card


# =============================================================================
# Session keys (Tool6 naming)
# =============================================================================
SS_ROWS = "tool6_summary_findings_rows"          # list[dict]
SS_LOCK = "tool6_summary_findings_lock"          # bool: user confirmed
SS_SOURCE_FP = "tool6_summary_findings_fp"       # str: signature of section5 data

# Outputs used by builder / step10
SS_SEVERITY_BY_NO = "tool6_severity_by_no"       # Dict[int, str]
SS_SEVERITY_BY_FINDING = "tool6_severity_by_finding"  # Dict[str, str]
SS_ADD_LEGEND = "tool6_add_legend"               # bool


# =============================================================================
# Small helpers (fast + safe)
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"t6.s8.{h}"


def _norm_sentence(v: Any) -> str:
    sv = _s(v)
    if not sv:
        return ""
    sv = " ".join(sv.split()).strip()
    if sv and sv not in ("—", "-"):
        if sv[-1] not in ".!?":
            sv += "."
    if sv and sv[0].isalpha():
        sv = sv[0].upper() + sv[1:]
    return sv


def _fp_section5(component_observations: Any) -> str:
    """
    ✅ Fast + reliable fingerprint:
    Uses titles + finding texts + recommendations count, but keeps it light.
    """
    if not isinstance(component_observations, list) or not component_observations:
        return "empty"

    pieces: List[str] = []
    try:
        for comp in component_observations[:12]:  # cap to keep it fast
            if not isinstance(comp, dict):
                continue
            ov = comp.get("observations_valid") or []
            if not isinstance(ov, list):
                continue
            for ob in ov[:20]:
                if not isinstance(ob, dict):
                    continue
                pieces.append(_s(ob.get("title")))
                # Step4: major_table findings
                mt = ob.get("major_table") or []
                if isinstance(mt, list):
                    for r in mt[:10]:
                        if isinstance(r, dict):
                            pieces.append(_s(r.get("finding")))
                            pieces.append(_s(r.get("Tools")))
                # Step4: recommendations list
                recs = ob.get("recommendations") or []
                if isinstance(recs, list):
                    pieces.append(f"recs={len([x for x in recs if _s(x)])}")
        raw = "|".join(pieces)
        return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    except Exception:
        return "unknown"


def _extract_from_section5(component_observations: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    ✅ Correct extraction for your current pipeline:
    Step 4 attaches to observations_valid:
      - major_table: list[{finding, Tools, photo...}]
      - recommendations: list[str]
    This Step 8 summarizes those into rows.
    """
    out: List[Dict[str, str]] = []

    for comp in component_observations or []:
        if not isinstance(comp, dict):
            continue
        ov = comp.get("observations_valid") or []
        if not isinstance(ov, list):
            continue

        for ob in ov:
            if not isinstance(ob, dict):
                continue

            mt = ob.get("major_table") or []
            recs = ob.get("recommendations") or []

            # Join recommendations into one sentence (summary row)
            reco_text = " ".join([_s(x) for x in recs if _s(x)]).strip()

            # Each finding row becomes one summary row
            if isinstance(mt, list) and mt:
                for r in mt:
                    if not isinstance(r, dict):
                        continue
                    f = _s(r.get("finding"))
                    if not f:
                        continue
                    out.append(
                        {
                            "finding": f,
                            "recommendation": reco_text or _s(r.get("recommendation")) or _s(r.get("corrective_action")),
                        }
                    )
            else:
                # Fallback: if no major_table but there is a recommendation
                if reco_text:
                    out.append({"finding": _s(ob.get("title")) or "Finding", "recommendation": reco_text})

    # Clean
    cleaned: List[Dict[str, str]] = []
    for d in out:
        f = _s(d.get("finding"))
        r = _s(d.get("recommendation"))
        if f:
            cleaned.append({"finding": f, "recommendation": r})
    return cleaned


def _default_rows(component_observations: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    extracted = _extract_from_section5(component_observations or [])
    rows: List[Dict[str, str]] = []
    for it in extracted:
        rows.append(
            {
                "No.": "",
                "Finding": _norm_sentence(it.get("finding")),
                "Severity": "Medium",
                "Recommendation / Corrective Action": _norm_sentence(it.get("recommendation")) or "—",
            }
        )
    if not rows:
        rows = [
            {"No.": "", "Finding": "", "Severity": "Medium", "Recommendation / Corrective Action": "—"},
            {"No.": "", "Finding": "", "Severity": "Medium", "Recommendation / Corrective Action": "—"},
            {"No.": "", "Finding": "", "Severity": "Medium", "Recommendation / Corrective Action": "—"},
        ]
    return rows


def _rows_to_payload(rows: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], Dict[int, str], Dict[str, str]]:
    """
    Outputs:
      - extracted list for DOC section: [{"finding":..., "recommendation":...}]
      - severity_by_no: {1:"High", ...}
      - severity_by_finding: {"finding text": "High", ...}
    """
    extracted: List[Dict[str, str]] = []
    severity_by_no: Dict[int, str] = {}
    severity_by_finding: Dict[str, str] = {}

    n = 0
    for r in rows or []:
        finding = _norm_sentence(r.get("Finding"))
        reco = _norm_sentence(r.get("Recommendation / Corrective Action")) or "—"
        sev = _s(r.get("Severity")) or "Medium"

        if not finding:
            continue

        n += 1
        extracted.append({"finding": finding, "recommendation": reco})
        severity_by_no[n] = sev
        severity_by_finding[finding] = sev

    return extracted, severity_by_no, severity_by_finding


def _ensure_state(component_observations: List[Dict[str, Any]]) -> None:
    ss = st.session_state
    ss.setdefault(SS_ROWS, [])
    ss.setdefault(SS_LOCK, False)
    ss.setdefault(SS_SOURCE_FP, "")

    ss.setdefault(SS_ADD_LEGEND, True)
    ss.setdefault(SS_SEVERITY_BY_NO, {})
    ss.setdefault(SS_SEVERITY_BY_FINDING, {})

    fp = _fp_section5(component_observations)

    # First time
    if not ss.get(SS_ROWS):
        ss[SS_ROWS] = _default_rows(component_observations)
        ss[SS_SOURCE_FP] = fp
        return

    # If confirmed, do not auto overwrite
    if bool(ss.get(SS_LOCK, False)):
        return

    # If section5 changed: refresh only if user hasn't typed meaningful content
    if ss.get(SS_SOURCE_FP) != fp:
        cur = ss.get(SS_ROWS) or []
        has_text = any(_s(r.get("Finding")) for r in cur if isinstance(r, dict))
        if not has_text:
            ss[SS_ROWS] = _default_rows(component_observations)
        ss[SS_SOURCE_FP] = fp


# =============================================================================
# Main renderer
# =============================================================================
def render_step(ctx: Tool6Context, *, title: str = "Step 8 — Summary of Findings") -> bool:
    if pd is None:
        st.error("pandas is required for Step 8. Please install pandas.")
        return False

    st.subheader(title)
    st.caption("Edit findings, severity, and recommendations. Changes are saved instantly.")

    # Source: merged observations (preferred)
    component_observations = st.session_state.get("tool6_component_observations_final")
    if component_observations is None:
        component_observations = st.session_state.get("component_observations", [])

    if not isinstance(component_observations, list):
        component_observations = []

    _ensure_state(component_observations)

    with st.container(border=True):
        card_open(
            "Summary of the findings",
            subtitle="Pulled from Step 3/4. You can edit severity and recommendations here.",
            variant="lg-variant-cyan",
        )

        # Toolbar
        colA, colB, colC = st.columns([1, 1, 2], vertical_alignment="center")
        with colA:
            st.session_state[SS_LOCK] = st.toggle(
                "Confirmed",
                value=bool(st.session_state.get(SS_LOCK, False)),
                key=_key("confirm_lock"),
                help="If ON, this step will not auto-refresh when Section 5 changes.",
            )
        with colB:
            if st.button("Reset from Section 5", use_container_width=True, key=_key("reset")):
                st.session_state[SS_ROWS] = _default_rows(component_observations)
                st.session_state[SS_SOURCE_FP] = _fp_section5(component_observations)
                st.session_state[SS_LOCK] = False
                st.rerun()
        with colC:
            st.session_state[SS_ADD_LEGEND] = st.toggle(
                "Add severity legend in report",
                value=bool(st.session_state.get(SS_ADD_LEGEND, True)),
                key=_key("legend"),
            )

        rows = st.session_state.get(SS_ROWS) or []
        for i, r in enumerate(rows, start=1):
            if isinstance(r, dict):
                r["No."] = str(i)

        df = pd.DataFrame(rows, columns=["No.", "Finding", "Severity", "Recommendation / Corrective Action"])

        edited_df = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "No.": st.column_config.TextColumn("No.", disabled=True, width="small"),
                "Finding": st.column_config.TextColumn("Finding", required=False, width="large"),
                "Severity": st.column_config.SelectboxColumn(
                    "Severity",
                    options=["High", "Medium", "Low"],
                    required=True,
                    width="small",
                ),
                "Recommendation / Corrective Action": st.column_config.TextColumn(
                    "Recommendation / Corrective Action",
                    required=False,
                    width="large",
                ),
            },
            key=_key("editor"),
        )

        # Autosave
        new_rows: List[Dict[str, str]] = []
        for _, r in edited_df.iterrows():
            new_rows.append(
                {
                    "No.": _s(r.get("No.")),
                    "Finding": _s(r.get("Finding")),
                    "Severity": _s(r.get("Severity")) or "Medium",
                    "Recommendation / Corrective Action": _s(r.get("Recommendation / Corrective Action")) or "—",
                }
            )
        st.session_state[SS_ROWS] = new_rows

        extracted, sev_by_no, sev_by_finding = _rows_to_payload(new_rows)

        # Store outputs for report builder / step10
        st.session_state[SS_SEVERITY_BY_NO] = sev_by_no
        st.session_state[SS_SEVERITY_BY_FINDING] = sev_by_finding

        # Optional compatibility: some builders read these keys
        st.session_state["tool6_summary_findings_extracted"] = extracted

        # Status
        st.divider()
        if extracted:
            status_card("Saved", f"Valid findings: {len(extracted)}", level="success")
        else:
            status_card("Empty", "Please enter at least one finding.", level="warning")

        card_close()

    return len(st.session_state.get("tool6_summary_findings_extracted", []) or []) >= 1
