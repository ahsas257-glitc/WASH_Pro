# src/Tools/steps/step_7_data_collection_methods.py
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Tuple

import streamlit as st

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card


# =============================================================================
# Session keys (Tool6 naming)
# =============================================================================
SS_CONFIRMED = "tool6_dcm_confirmed"
SS_LIST_TEXT = "tool6_dcm_list_text"
SS_NARR_TEXT = "tool6_dcm_narrative_text"

# Perf/cache
SS_DCM_FINGERPRINT = "tool6_dcm_fp"
SS_DCM_AUTO_LIST = "tool6_dcm_auto_list"
SS_DCM_AUTO_NARR = "tool6_dcm_auto_narr"


# =============================================================================
# Flags (must match report_sections/data_collection_methods.py)
# =============================================================================
FLAGS: List[Tuple[str, str]] = [
    ("D0_direct_observation", "Direct technical observation"),
    ("D0_key_informant_interview", "Key informant interviews (CDC/IP/Contractor)"),
    ("D0_photos_taken", "Geo-referenced photos were taken"),
    ("D0_gps_points_recorded", "GPS points verified/recorded"),

    ("D1_contract_available", "Contract documents available"),
    ("D1_journal_available", "Site journal / progress records available"),
    ("D2_boq_available", "BOQ available"),
    ("D2_drawings_available", "Approved technical drawings available"),
    ("D3_geophysical_tests_available", "Geophysical/Hydrological tests available"),
    ("D4_water_quality_tests_available", "Water quality tests available"),
    ("D4_pump_test_results_available", "Pump test results available"),
]


# =============================================================================
# Helpers
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"t6.s7.{h}"


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def _ensure_state() -> None:
    ss = st.session_state
    ss.setdefault(SS_CONFIRMED, False)
    ss.setdefault(SS_LIST_TEXT, "")
    ss.setdefault(SS_NARR_TEXT, "")

    ss.setdefault(SS_DCM_FINGERPRINT, "")
    ss.setdefault(SS_DCM_AUTO_LIST, [])
    ss.setdefault(SS_DCM_AUTO_NARR, "")

    ss.setdefault("general_info_overrides", {})
    ovr = ss["general_info_overrides"]

    # Ensure all flags exist
    for k, _ in FLAGS:
        ovr.setdefault(k, False)

    ss["general_info_overrides"] = ovr


def _build_doc_review_phrase(ovr: Dict[str, Any]) -> str:
    reviewed: List[str] = []
    if bool(ovr.get("D2_boq_available")):
        reviewed.append("Bill of Quantities (BOQ)")
    if bool(ovr.get("D2_drawings_available")):
        reviewed.append("approved technical drawings")
    if bool(ovr.get("D1_contract_available")):
        reviewed.append("contract documents")
    if bool(ovr.get("D1_journal_available")):
        reviewed.append("site journal and progress records")
    if bool(ovr.get("D3_geophysical_tests_available")):
        reviewed.append("geophysical and hydrological test reports")
    if bool(ovr.get("D4_water_quality_tests_available")):
        reviewed.append("water quality test results")
    if bool(ovr.get("D4_pump_test_results_available")):
        reviewed.append("pump test results")

    if not reviewed:
        return ""
    return "Review of project documentation, including " + ", ".join(reviewed) + "."


def _auto_generate(ovr: Dict[str, Any]) -> Tuple[List[str], str]:
    methods: List[str] = []

    if bool(ovr.get("D0_direct_observation")):
        methods.append("Direct technical observation of work progress and construction quality on-site.")

    doc_review = _build_doc_review_phrase(ovr)
    if doc_review:
        methods.append(doc_review)

    if bool(ovr.get("D0_key_informant_interview")):
        methods.append(
            "Semi-structured interviews with technical staff of the contracted company, implementing partner personnel, "
            "and Community Development Council (CDC) members."
        )

    if bool(ovr.get("D0_photos_taken")):
        methods.append(
            "Collection and review of geo-referenced photographic evidence to verify physical progress and workmanship."
        )

    if bool(ovr.get("D0_gps_points_recorded")):
        methods.append(
            "Verification of GPS coordinates and location data to confirm site positioning and component alignment."
        )

    if not methods:
        methods.append(
            "The monitoring visit applied standard Third-Party Monitoring (TPM) data collection techniques in line with UNICEF WASH guidelines."
        )

    narrative = (
        "The Third-Party Monitoring (TPM) assessment was conducted using a structured mixed-methods approach, combining "
        "direct on-site technical observation, systematic review of available project documentation, and qualitative "
        "engagement with relevant stakeholders. The monitoring focused on verifying construction quality, system "
        "functionality, and compliance with approved designs and contractual requirements, while identifying technical "
        "and operational risks that may affect performance and sustainability. Physical and documentary evidence was "
        "assessed across all applicable project components, and findings were analyzed, categorized by severity, and "
        "linked to practical corrective actions in accordance with UNICEF WASH standards and third-party monitoring protocols."
    )
    return methods, narrative


def _compute_and_cache_auto_text(ovr: Dict[str, Any]) -> Tuple[List[str], str]:
    """
    ✅ Performance: generate auto text only when flags change.
    """
    fp_source = "|".join([f"{k}={int(bool(ovr.get(k)))}" for k, _ in FLAGS])
    fp = _sha1(fp_source)

    if st.session_state.get(SS_DCM_FINGERPRINT) != fp:
        methods, narrative = _auto_generate(ovr)
        st.session_state[SS_DCM_FINGERPRINT] = fp
        st.session_state[SS_DCM_AUTO_LIST] = methods
        st.session_state[SS_DCM_AUTO_NARR] = narrative

        # If user hasn't confirmed, keep editor synced to latest auto text unless they already typed
        if not bool(st.session_state.get(SS_CONFIRMED, False)):
            if not _s(st.session_state.get(SS_LIST_TEXT)):
                st.session_state[SS_LIST_TEXT] = "\n".join(methods)
            if not _s(st.session_state.get(SS_NARR_TEXT)):
                st.session_state[SS_NARR_TEXT] = narrative

    return (
        st.session_state.get(SS_DCM_AUTO_LIST, []) or [],
        _s(st.session_state.get(SS_DCM_AUTO_NARR)),
    )


# =============================================================================
# MAIN
# =============================================================================
def render_step(ctx: Tool6Context) -> bool:
    """
    Step 7 — Data Collection Methods
    - Toggle evidence & methods sources
    - Auto-generate list + narrative (cached)
    - Allow user edit
    - Require confirm
    - Save into general_info_overrides:
        D_methods_list_text
        D_methods_narrative_text
    """
    _ = ctx
    _ensure_state()
    ss = st.session_state
    ovr: Dict[str, Any] = ss.get("general_info_overrides", {}) or {}

    st.subheader("Step 7 — Data Collection Methods")

    with st.container(border=True):
        card_open(
            "Data Collection Methods",
            subtitle="Select available evidence and methods, then review/edit the text before confirming.",
            variant="lg-variant-cyan",
        )

        left, right = st.columns([1.05, 1], gap="large")

        # ---------------- LEFT: toggles ----------------
        with left:
            st.markdown("### 1) Select inputs")

            grp1 = st.container(border=True)
            with grp1:
                st.markdown("**Field methods**")
                for key, label in FLAGS[:4]:
                    ovr[key] = st.toggle(label, value=bool(ovr.get(key)), key=_key("flag", key))

            grp2 = st.container(border=True)
            with grp2:
                st.markdown("**Documentary evidence**")
                for key, label in FLAGS[4:]:
                    ovr[key] = st.toggle(label, value=bool(ovr.get(key)), key=_key("flag", key))

            st.divider()

            auto1, auto2 = st.columns([1, 1], gap="small")
            with auto1:
                if st.button("Auto-generate text", use_container_width=True, key=_key("auto")):
                    methods, narrative = _auto_generate(ovr)
                    ss[SS_LIST_TEXT] = "\n".join(methods)
                    ss[SS_NARR_TEXT] = narrative
                    ss[SS_CONFIRMED] = False
                    # also refresh cache
                    ss[SS_DCM_FINGERPRINT] = ""
                    status_card("Generated", "Text was generated. Review & edit on the right, then confirm.", level="success")

            with auto2:
                if st.button("Reset (clear edits)", use_container_width=True, key=_key("reset")):
                    ss[SS_LIST_TEXT] = ""
                    ss[SS_NARR_TEXT] = ""
                    ss[SS_CONFIRMED] = False

            st.caption("Tip: Even without clicking Auto-generate, preview is based on current toggles.")

        # ---------------- RIGHT: preview + editor ----------------
        with right:
            st.markdown("### 2) Preview & edit")

            auto_list, auto_narr = _compute_and_cache_auto_text(ovr)

            list_text = _s(ss.get(SS_LIST_TEXT)) or "\n".join(auto_list)
            narr_text = _s(ss.get(SS_NARR_TEXT)) or auto_narr

            tabs = st.tabs(["Preview", "Edit"])

            with tabs[0]:
                st.markdown("**Numbered methods (preview):**")
                items = [ln.strip() for ln in list_text.splitlines() if ln.strip()] or auto_list
                for i, it in enumerate(items, start=1):
                    st.write(f"{i}. {it}")

                st.markdown("---")
                st.markdown("**Narrative paragraph (preview):**")
                st.write(narr_text)

            with tabs[1]:
                ss[SS_LIST_TEXT] = st.text_area(
                    "Numbered methods (one per line)",
                    value=list_text,
                    height=170,
                    key=_key("list_text"),
                    help="Each line becomes one numbered item in the report.",
                )

                ss[SS_NARR_TEXT] = st.text_area(
                    "Narrative paragraph",
                    value=narr_text,
                    height=220,
                    key=_key("narr_text"),
                )

            st.divider()

            ss[SS_CONFIRMED] = st.checkbox(
                "I confirm this section is correct and ready to be included in the report.",
                value=bool(ss.get(SS_CONFIRMED)),
                key=_key("confirm"),
            )

        # ---------------- SAVE to overrides for DOCX ----------------
        ovr["D_methods_list_text"] = _s(ss.get(SS_LIST_TEXT)) or "\n".join(auto_list)
        ovr["D_methods_narrative_text"] = _s(ss.get(SS_NARR_TEXT)) or auto_narr
        ss["general_info_overrides"] = ovr

        if ss[SS_CONFIRMED]:
            status_card("Confirmed", "This section will be included in the generated DOCX.", level="success")
        else:
            status_card("Not confirmed", "Please review and confirm to continue.", level="warning")

        card_close()

    # Validation: must confirm + must have at least 1 method line (or auto list)
    items_final = [ln.strip() for ln in (_s(ss.get(SS_LIST_TEXT)) or "").splitlines() if ln.strip()] or auto_list
    return bool(ss.get(SS_CONFIRMED)) and bool(items_final)
