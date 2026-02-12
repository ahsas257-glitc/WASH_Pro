# src/Tools/steps/step_7_data_collection_methods.py
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from src.Tools.utils.types import Tool6Context
from design.components.cards import pure_glass_panel
from design.components.base_tool_ui import card_close, status_card


# =============================================================================
# Session keys (Tool6 naming)
# =============================================================================
SS_CONFIRMED = "tool6_dcm_confirmed"
SS_LIST_TEXT = "tool6_dcm_list_text"
SS_NARR_TEXT = "tool6_dcm_narrative_text"

# Perf/cache (auto text)
SS_DCM_HASH = "tool6_dcm_hash"
SS_DCM_AUTO_LIST = "tool6_dcm_auto_list"
SS_DCM_AUTO_NARR = "tool6_dcm_auto_narr"

# UX / Advanced
SS_DCM_DIRTY_LIST = "tool6_dcm_dirty_list"
SS_DCM_DIRTY_NARR = "tool6_dcm_dirty_narr"
SS_DCM_SHOW_ONLY_SELECTED = "tool6_dcm_show_only_selected"
SS_DCM_SHOW_DIFF = "tool6_dcm_show_diff"

# Controls
SS_DCM_STYLE = "tool6_dcm_style"                 # "Short"|"Standard"|"Detailed"
SS_DCM_TONE = "tool6_dcm_tone"                   # "Neutral"|"Formal"|"Action-oriented"
SS_DCM_PREVIEW_MODE = "tool6_dcm_preview_mode"   # "Numbered"|"Bullets"
SS_DCM_TEMPLATE = "tool6_dcm_template"           # template name

# Translation (one-click, pluggable)
SS_DCM_TRANSLATE_TARGET = "tool6_dcm_translate_target"  # "English"|"Persian/Dari"
SS_DCM_TRANSLATE_SOURCE = "tool6_dcm_translate_source"  # "Edited"|"Auto"

# Internal fast keys
SS_DCM_UI_MOBILE = "tool6_dcm_is_mobile"
SS_DCM_LAST_WIDGET_FP = "tool6_dcm_last_widget_fp"

# NEW: navigation/stepper bridge keys (safe no-op if parent doesn't use them)
SS_STEP7_READY = "tool6_step7_ready_for_next"
SS_NAV_NEXT_REQUESTED = "tool6_nav_next_requested"

# CSS injected guard
SS_S7_CSS_DONE = "tool6_s7_css_done"


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

# Optional modern “new-tech” methods (stored in overrides)
EXTRA_METHODS: List[Tuple[str, str]] = [
    ("D0_drone_imagery", "Drone imagery / aerial visual verification (if feasible)"),
    ("D0_mobile_gis", "Mobile GIS / digital forms with geotagging (ODK/Kobo-like)"),
    ("D0_remote_validation", "Remote validation (photos/video call) when access is constrained"),
    ("D0_sensor_spotcheck", "Spot-check using basic sensors/meters (flow/pressure where possible)"),
    ("D0_stakeholder_fgd", "Focused group discussions (community users)"),
    ("D0_risk_checklist", "Structured risk checklist / compliance scoring"),
    ("D0_triangulation", "Triangulation across sources (field + docs + stakeholders)"),
]


# =============================================================================
# UI config
# =============================================================================
class UIConfig:
    MOBILE_BREAKPOINT_PX = 900

    LIST_EDITOR_HEIGHT = 180
    NARR_EDITOR_HEIGHT = 260

    DEFAULT_STYLE = "Standard"
    DEFAULT_TONE = "Neutral"
    DEFAULT_PREVIEW = "Numbered"
    DEFAULT_TEMPLATE = "Standard TPM (Balanced)"

    TRANSLATE_TARGETS = ["English", "Persian/Dari"]

    MAX_CONTENT_WIDTH_PX = 1180


# =============================================================================
# Template library
# =============================================================================
TEMPLATE_LIBRARY: Dict[str, Dict[str, Any]] = {
    "Standard TPM (Balanced)": {"style": "Standard", "tone": "Neutral", "preview": "Numbered"},
    "Compact (Short + Bullets)": {"style": "Short", "tone": "Neutral", "preview": "Bullets"},
    "Donor/Stakeholder (Formal + Detailed)": {"style": "Detailed", "tone": "Formal", "preview": "Numbered"},
    "Action Follow-up (Action-oriented)": {"style": "Standard", "tone": "Action-oriented", "preview": "Numbered"},
}


# =============================================================================
# Helpers (fast, pure)
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()
    return f"t6.s7.{h}"


def _split_paragraphs(text: str) -> str:
    t = (text or "").replace("\r\n", "\n")
    t = "\n".join([ln.rstrip() for ln in t.split("\n")])
    while "\n\n\n" in t:
        t = t.replace("\n\n\n", "\n\n")
    return t.strip()


def _lines(text: str) -> List[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _word_char_count(text: str) -> Tuple[int, int]:
    t = _s(text)
    if not t:
        return 0, 0
    words = len([w for w in re.split(r"\s+", t) if w.strip()])
    return words, len(t)


def _simple_diff(a: str, b: str, max_lines: int = 140) -> str:
    a_lines = (a or "").splitlines()
    b_lines = (b or "").splitlines()

    out: List[str] = ["Legend: - removed | + added |   unchanged", ""]
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
        out.extend(["", "… diff truncated …"])

    return "\n".join(out)


def _safe_index(options: List[str], value: str, default_value: str) -> int:
    v = value if value in options else default_value
    try:
        return options.index(v)
    except Exception:
        return 0


# =============================================================================
# UI styling (inject once to reduce flicker)
# =============================================================================
def _inject_ui_css_once() -> None:
    ss = st.session_state
    if ss.get(SS_S7_CSS_DONE):
        return

    st.markdown(
        f"""
<style>
.t6-s7-wrap {{
  max-width: {UIConfig.MAX_CONTENT_WIDTH_PX}px;
  margin-left: auto;
  margin-right: auto;
}}

div[data-testid="stHorizontalBlock"] {{
  align-items: stretch;
}}
div[data-testid="column"] {{
  display: flex;
  flex-direction: column;
  align-self: stretch;
}}
[data-testid="stVerticalBlock"] {{ gap: 0.70rem; }}

div[data-testid="stTextArea"] textarea,
div[data-testid="stTextInput"] input,
div[data-testid="stSelectbox"] div[role="combobox"],
div[data-testid="stNumberInput"] input {{
  width: 100% !important;
}}

.t6-s7-sticky {{
  position: sticky;
  top: 0.25rem;
  z-index: 80;
  backdrop-filter: blur(10px);
  padding: 0.65rem 0.75rem;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.10);
  background: rgba(15,15,18,0.55);
  margin-bottom: 0.85rem;
}}
@media (max-width: {UIConfig.MOBILE_BREAKPOINT_PX}px) {{
  div[data-testid="column"] {{
    width: 100% !important;
    flex: 1 1 100% !important;
  }}
  .t6-s7-sticky {{
    position: relative !important;
    top: unset !important;
  }}
}}
.t6-s7-subtle {{
  opacity: 0.86;
  font-size: 0.92rem;
}}
.t6-s7-row {{
  display:flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}}
.t6-s7-pill {{
  border: 1px solid rgba(255,255,255,0.14);
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.84rem;
  opacity: 0.9;
}}
.t6-s7-card .stMarkdown p {{
  margin-top: 0.2rem;
  margin-bottom: 0.2rem;
}}
</style>
""",
        unsafe_allow_html=True,
    )
    ss[SS_S7_CSS_DONE] = True


def _card(title: str, body_fn, *, help_text: str = "") -> None:
    # Unified card wrapper (consistent edges + theme tokens)
    with pure_glass_panel(title=title, subtitle=help_text, variant="default", divider=False):
        body_fn()



# =============================================================================
# Translation (pluggable)
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
            "Register a callable in st.session_state['tool6_translate_fn'] that accepts (text, target) -> str."
        )
    try:
        out = fn(t, target)
        return _split_paragraphs(out), None
    except Exception as e:
        return t, f"Translation failed: {e}"


# =============================================================================
# State init
# =============================================================================
def _ensure_state() -> None:
    ss = st.session_state
    ss.setdefault(SS_CONFIRMED, False)
    ss.setdefault(SS_LIST_TEXT, "")
    ss.setdefault(SS_NARR_TEXT, "")

    ss.setdefault(SS_DCM_HASH, "")
    ss.setdefault(SS_DCM_AUTO_LIST, [])
    ss.setdefault(SS_DCM_AUTO_NARR, "")

    ss.setdefault(SS_DCM_DIRTY_LIST, False)
    ss.setdefault(SS_DCM_DIRTY_NARR, False)
    ss.setdefault(SS_DCM_SHOW_ONLY_SELECTED, False)
    ss.setdefault(SS_DCM_SHOW_DIFF, False)

    ss.setdefault(SS_DCM_STYLE, UIConfig.DEFAULT_STYLE)
    ss.setdefault(SS_DCM_TONE, UIConfig.DEFAULT_TONE)
    ss.setdefault(SS_DCM_PREVIEW_MODE, UIConfig.DEFAULT_PREVIEW)

    ss.setdefault(SS_DCM_TEMPLATE, UIConfig.DEFAULT_TEMPLATE)
    if ss[SS_DCM_TEMPLATE] not in TEMPLATE_LIBRARY:
        ss[SS_DCM_TEMPLATE] = UIConfig.DEFAULT_TEMPLATE

    ss.setdefault(SS_DCM_TRANSLATE_TARGET, "Persian/Dari")
    if ss[SS_DCM_TRANSLATE_TARGET] not in UIConfig.TRANSLATE_TARGETS:
        ss[SS_DCM_TRANSLATE_TARGET] = "Persian/Dari"

    ss.setdefault(SS_DCM_TRANSLATE_SOURCE, "Edited")
    if ss[SS_DCM_TRANSLATE_SOURCE] not in ("Edited", "Auto"):
        ss[SS_DCM_TRANSLATE_SOURCE] = "Edited"

    ss.setdefault(SS_DCM_UI_MOBILE, False)
    ss.setdefault(SS_DCM_LAST_WIDGET_FP, "")

    ss.setdefault(SS_STEP7_READY, False)
    ss.setdefault(SS_NAV_NEXT_REQUESTED, False)

    ss.setdefault("general_info_overrides", {})
    ovr = ss["general_info_overrides"]

    for k, _ in FLAGS:
        ovr.setdefault(k, False)
    for k, _ in EXTRA_METHODS:
        ovr.setdefault(k, False)

    ss["general_info_overrides"] = ovr


# =============================================================================
# Generation logic
# =============================================================================
def _build_doc_review_phrase(ovr: Dict[str, Any], style: str) -> str:
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

    if style == "Short":
        return "Review of available project documentation (BOQ/drawings/contract and relevant test records)."
    if style == "Detailed":
        return "Review of project documentation, including " + ", ".join(reviewed) + ", to verify compliance with approved specifications."
    return "Review of project documentation, including " + ", ".join(reviewed) + "."


def _tone_bits(tone: str) -> Dict[str, str]:
    tone = tone or UIConfig.DEFAULT_TONE
    if tone == "Formal":
        return {
            "opening": "The Third-Party Monitoring (TPM) assessment was conducted using a structured mixed-methods approach, ",
            "focus": "The monitoring emphasized verification of construction quality, system performance, and compliance with approved designs and contractual requirements. ",
            "closing": "Evidence was assessed across applicable project components, and findings were analyzed and linked to corrective actions in line with UNICEF WASH standards and TPM protocols.",
        }
    if tone == "Action-oriented":
        return {
            "opening": "The TPM assessment applied a structured mixed-methods approach to enable clear verification and follow-up, ",
            "focus": "The monitoring prioritized actionable verification of quality, functionality, and compliance, and aimed to surface risks that require corrective action. ",
            "closing": "Evidence was reviewed across applicable components and translated into clear findings with practical follow-up actions aligned with UNICEF WASH standards and TPM protocols.",
        }
    return {
        "opening": "The Third-Party Monitoring (TPM) assessment was conducted using a structured mixed-methods approach, ",
        "focus": "The monitoring focused on verifying construction quality, functionality, and compliance with approved designs and contractual requirements, while identifying risks that may affect performance and sustainability. ",
        "closing": "Evidence was assessed across applicable project components, and findings were analyzed and linked to practical corrective actions in line with UNICEF WASH standards and TPM protocols.",
    }


def _auto_generate_methods_list(ovr: Dict[str, Any], style: str, tone: str) -> List[str]:
    style = style or UIConfig.DEFAULT_STYLE
    _ = tone

    methods: List[str] = []

    if bool(ovr.get("D0_direct_observation")):
        if style == "Short":
            methods.append("Direct technical observation on-site.")
        elif style == "Detailed":
            methods.append(
                "Direct on-site technical observation to verify work progress, construction quality, and functionality against approved specifications."
            )
        else:
            methods.append("Direct technical observation of work progress and construction quality on-site.")

    doc_review = _build_doc_review_phrase(ovr, style=style)
    if doc_review:
        methods.append(doc_review)

    if bool(ovr.get("D0_key_informant_interview")):
        if style == "Short":
            methods.append("Key informant interviews (CDC/IP/Contractor).")
        else:
            methods.append(
                "Semi-structured interviews with technical staff of the contracted company, implementing partner personnel, "
                "and Community Development Council (CDC) members."
            )

    if bool(ovr.get("D0_photos_taken")):
        methods.append(
            "Geo-referenced photos reviewed."
            if style == "Short"
            else "Collection and review of geo-referenced photographic evidence to verify physical progress and workmanship."
        )

    if bool(ovr.get("D0_gps_points_recorded")):
        methods.append(
            "GPS points verified/recorded."
            if style == "Short"
            else "Verification of GPS coordinates and location data to confirm site positioning and component alignment."
        )

    # optional modern methods
    if bool(ovr.get("D0_drone_imagery")):
        methods.append("Aerial verification using drone imagery was used where feasible to corroborate site conditions and layout.")
    if bool(ovr.get("D0_mobile_gis")):
        methods.append("Digital data collection using mobile GIS forms with geotagging was applied to improve traceability and consistency.")
    if bool(ovr.get("D0_remote_validation")):
        methods.append("Remote validation (photo/video-based checks) supplemented field verification when physical access was constrained.")
    if bool(ovr.get("D0_sensor_spotcheck")):
        methods.append("Spot-check measurements using basic meters/sensors were used where feasible to validate functionality.")
    if bool(ovr.get("D0_stakeholder_fgd")):
        methods.append("Focused group discussions with end-users were used to validate service delivery and user experience.")
    if bool(ovr.get("D0_risk_checklist")):
        methods.append("A structured risk/compliance checklist was used to standardize observation and strengthen comparability.")
    if bool(ovr.get("D0_triangulation")):
        methods.append("Triangulation across multiple sources (field, documents, stakeholder inputs) was applied to validate findings.")

    if not methods:
        methods.append(
            "The monitoring visit applied standard Third-Party Monitoring (TPM) data collection techniques in line with UNICEF WASH guidelines."
        )

    return methods


def _auto_generate_narrative_dynamic(ovr: Dict[str, Any], style: str, tone: str) -> str:
    style = style or UIConfig.DEFAULT_STYLE
    tb = _tone_bits(tone)

    direct_obs = bool(ovr.get("D0_direct_observation"))
    interviews = bool(ovr.get("D0_key_informant_interview"))
    photos = bool(ovr.get("D0_photos_taken"))
    gps = bool(ovr.get("D0_gps_points_recorded"))

    drone = bool(ovr.get("D0_drone_imagery"))
    mobile = bool(ovr.get("D0_mobile_gis"))
    remote = bool(ovr.get("D0_remote_validation"))
    sensors = bool(ovr.get("D0_sensor_spotcheck"))
    fgd = bool(ovr.get("D0_stakeholder_fgd"))
    checklist = bool(ovr.get("D0_risk_checklist"))
    triang = bool(ovr.get("D0_triangulation"))

    any_docs = any(
        bool(ovr.get(k))
        for k in [
            "D1_contract_available",
            "D1_journal_available",
            "D2_boq_available",
            "D2_drawings_available",
            "D3_geophysical_tests_available",
            "D4_water_quality_tests_available",
            "D4_pump_test_results_available",
        ]
    )

    if style == "Short":
        opening = tb["opening"] + "combining field verification, documentation review, and stakeholder engagement where applicable."
    elif style == "Detailed":
        opening = (
            tb["opening"]
            + "combining direct on-site verification, systematic review of available project documentation, and qualitative engagement "
              "with relevant stakeholders to triangulate evidence and validate reported progress."
        )
    else:
        opening = tb["opening"] + "combining field-based verification, review of available project documentation, and qualitative engagement with relevant stakeholders."

    field_bits: List[str] = [
        "Direct on-site technical observation was used to verify workmanship, progress, and functionality."
        if direct_obs
        else "Field-based technical observation was applied based on available verification inputs during the visit.",
        "Geo-referenced photographic evidence was collected/reviewed to substantiate observed conditions."
        if photos
        else (
            "Photographic evidence was limited; observations relied on available verification inputs."
            if style != "Detailed"
            else "Photographic evidence was limited; observations relied on available in-person verification and documentation where applicable."
        ),
        "GPS coordinates were verified/recorded to confirm site positioning and component alignment."
        if gps
        else (
            "GPS verification was not emphasized."
            if style == "Short"
            else "GPS verification was not emphasized; location confirmation relied on available site references and documentation where applicable."
        ),
    ]

    tech_bits: List[str] = []
    if drone:
        tech_bits.append("Aerial verification (drone imagery) was used where feasible to corroborate layout and physical progress.")
    if mobile:
        tech_bits.append("Digital mobile GIS forms with geotagging were used to improve traceability and data quality.")
    if remote:
        tech_bits.append("Remote validation (photo/video-based checks) supplemented verification where access was constrained.")
    if sensors:
        tech_bits.append("Basic spot-check measurements (e.g., flow/pressure where feasible) were used to validate functionality.")
    if fgd:
        tech_bits.append("End-user discussions were used to validate service delivery and user experience.")
    if checklist:
        tech_bits.append("A structured checklist supported consistent scoring and compliance verification.")
    if triang:
        tech_bits.append("Triangulation across sources strengthened validity of observations and conclusions.")

    if any_docs:
        doc_phrase = _build_doc_review_phrase(ovr, style=style)
        doc_sentence = doc_phrase if doc_phrase else "Project documentation was reviewed to validate compliance with approved specifications and contractual requirements."
    else:
        doc_sentence = (
            "Documentary evidence was limited during the visit."
            if style == "Short"
            else "Documentary evidence was limited; therefore, compliance verification relied more heavily on field observations and stakeholder inputs."
        )

    if interviews:
        stakeholder_sentence = (
            "Key informant discussions were held to triangulate reported progress and operational arrangements."
            if style == "Short"
            else (
                "Semi-structured discussions were held with key informants (CDC members, implementing partner staff, and contractor personnel) "
                "to triangulate reported progress, clarify technical decisions, and validate operation and maintenance arrangements."
            )
        )
    else:
        stakeholder_sentence = (
            "Stakeholder engagement was limited."
            if style == "Short"
            else "Stakeholder engagement was limited; therefore, reported progress and operational arrangements were verified primarily through field and documentary checks."
        )

    focus = tb["focus"]
    closing = tb["closing"]

    if style == "Short":
        narrative = " ".join([opening, focus, closing])
    else:
        narrative = " ".join(
            [opening, " ".join(field_bits)]
            + ([" ".join(tech_bits)] if tech_bits else [])
            + [doc_sentence, stakeholder_sentence, focus, closing]
        )

    return _split_paragraphs(narrative)


def _auto_generate(ovr: Dict[str, Any], style: str, tone: str) -> Tuple[List[str], str]:
    return (
        _auto_generate_methods_list(ovr, style=style, tone=tone),
        _auto_generate_narrative_dynamic(ovr, style=style, tone=tone),
    )


def _fingerprint_core(ovr: Dict[str, Any], style: str, tone: str) -> str:
    parts = [f"{k}={int(bool(ovr.get(k)))}" for k, _ in (FLAGS + EXTRA_METHODS)]
    parts.extend([f"style={_s(style)}", f"tone={_s(tone)}"])
    return _sha1("|".join(parts))


def _compute_and_cache_auto_text(ovr: Dict[str, Any]) -> Tuple[List[str], str]:
    ss = st.session_state
    fp = _fingerprint_core(ovr, style=_s(ss.get(SS_DCM_STYLE)), tone=_s(ss.get(SS_DCM_TONE)))

    if ss.get(SS_DCM_HASH) != fp:
        methods, narrative = _auto_generate(ovr, style=_s(ss.get(SS_DCM_STYLE)), tone=_s(ss.get(SS_DCM_TONE)))
        ss[SS_DCM_HASH] = fp
        ss[SS_DCM_AUTO_LIST] = methods
        ss[SS_DCM_AUTO_NARR] = narrative

        # Never clobber edits if confirmed; otherwise update live if not dirty
        if not bool(ss.get(SS_CONFIRMED, False)):
            if not bool(ss.get(SS_DCM_DIRTY_LIST, False)):
                ss[SS_LIST_TEXT] = "\n".join(methods)
            if not bool(ss.get(SS_DCM_DIRTY_NARR, False)):
                ss[SS_NARR_TEXT] = narrative

    return ss.get(SS_DCM_AUTO_LIST, []) or [], _s(ss.get(SS_DCM_AUTO_NARR))


def _apply_template(template_name: str) -> None:
    ss = st.session_state
    tpl = TEMPLATE_LIBRARY.get(template_name, TEMPLATE_LIBRARY[UIConfig.DEFAULT_TEMPLATE])

    ss[SS_DCM_STYLE] = tpl.get("style", UIConfig.DEFAULT_STYLE)
    ss[SS_DCM_TONE] = tpl.get("tone", UIConfig.DEFAULT_TONE)
    ss[SS_DCM_PREVIEW_MODE] = tpl.get("preview", UIConfig.DEFAULT_PREVIEW)

    ss[SS_DCM_HASH] = ""
    ss[SS_DCM_DIRTY_LIST] = False
    ss[SS_DCM_DIRTY_NARR] = False
    ss[SS_CONFIRMED] = False


# =============================================================================
# Rendering helpers
# =============================================================================
def _render_methods_preview(items: List[str], mode: str) -> None:
    if not items:
        st.info("No methods to preview.")
        return

    mode = mode or UIConfig.DEFAULT_PREVIEW
    if mode == "Bullets":
        for it in items:
            st.markdown(f"- {it}")
    else:
        for i, it in enumerate(items, start=1):
            st.markdown(f"{i}. {it}")


def _sync_ovr_from_widget_state(ovr: Dict[str, Any], widget_key: str, flag_key: str) -> None:
    ovr[flag_key] = bool(st.session_state.get(widget_key, False))


def _widget_fp_for_selections(ovr: Dict[str, Any]) -> str:
    parts = [f"{k}={int(bool(ovr.get(k)))}" for k, _ in (FLAGS + EXTRA_METHODS)]
    return _sha1("|".join(parts))


# =============================================================================
# UI blocks (NO fragments: stable + predictable reruns)
# =============================================================================
def _sticky_bar() -> None:
    ss = st.session_state
    st.markdown("<div class='t6-s7-sticky'>", unsafe_allow_html=True)
    a1, a2, a3, a4, a5, a6 = st.columns([1.15, 1.15, 1.2, 1.2, 1.2, 1.3], gap="small")

    with a1:
        if st.button("Regenerate", use_container_width=True, key=_key("regen")):
            ss[SS_DCM_HASH] = ""
            ss[SS_DCM_DIRTY_LIST] = False
            ss[SS_DCM_DIRTY_NARR] = False
            ss[SS_CONFIRMED] = False

    with a2:
        if st.button("Reset to Auto", use_container_width=True, key=_key("reset_auto")):
            ss[SS_DCM_DIRTY_LIST] = False
            ss[SS_DCM_DIRTY_NARR] = False
            ss[SS_CONFIRMED] = False
            ss[SS_DCM_HASH] = ""

    with a3:
        st.toggle(
            "Show Diff",
            key=SS_DCM_SHOW_DIFF,
            help="Compare edited text vs latest auto text.",
        )

    with a4:
        st.toggle(
            "Show only selected",
            key=SS_DCM_SHOW_ONLY_SELECTED,
            help="Hide unselected options to reduce scrolling.",
        )

    with a5:
        st.toggle(
            "Confirmed",
            key=SS_CONFIRMED,
            help="When confirmed, this section is locked and used in DOCX.",
        )

    st.markdown("</div>", unsafe_allow_html=True)


def _draft_left_panel(ovr: Dict[str, Any]) -> None:
    ss = st.session_state
    show_only = bool(ss.get(SS_DCM_SHOW_ONLY_SELECTED, False))
    locked = bool(ss.get(SS_CONFIRMED, False))

    def _flag_widget_key(flag_key: str) -> str:
        return _key("flag", flag_key)

    def _render_group(title: str, items: List[Tuple[str, str]], *, expanded: bool = True) -> None:
        with st.expander(title, expanded=expanded):
            for flag_key, label in items:
                wkey = _flag_widget_key(flag_key)
                if wkey not in ss:
                    ss[wkey] = bool(ovr.get(flag_key, False))
                if show_only and not bool(ss.get(wkey, False)):
                    continue

                st.toggle(label, value=bool(ss.get(wkey, False)), key=wkey, disabled=locked)
                _sync_ovr_from_widget_state(ovr, wkey, flag_key)

    _card(
        "1) Select inputs",
        lambda: (
            _render_group("Field methods", FLAGS[:4], expanded=True),
            _render_group("Documentary evidence", FLAGS[4:], expanded=True),
            _render_group("Optional modern methods", EXTRA_METHODS, expanded=False),
            st.markdown(
                "<div class='t6-s7-subtle'>Selections update the draft instantly (unless confirmed). "
                "Use “Show only selected” to keep this short.</div>",
                unsafe_allow_html=True,
            ),
        ),
    )


def _draft_right_panel(ctx: Tool6Context, ovr: Dict[str, Any]) -> None:
    ss = st.session_state
    locked = bool(ss.get(SS_CONFIRMED, False))

    # Instant update trigger for selections -> rebuild auto
    widget_fp = _widget_fp_for_selections(ovr)
    if ss.get(SS_DCM_LAST_WIDGET_FP) != widget_fp:
        ss[SS_DCM_LAST_WIDGET_FP] = widget_fp
        ss[SS_DCM_HASH] = ""

    auto_list, auto_narr = _compute_and_cache_auto_text(ovr)

    list_text_current = _s(ss.get(SS_LIST_TEXT)) or "\n".join(auto_list)
    narr_text_current = _s(ss.get(SS_NARR_TEXT)) or auto_narr

    def _editor_block(title: str, value: str, height: int, key: str, help_text: str, disabled: bool) -> str:
        st.markdown(f"**{title} (Editor)**")
        return st.text_area(
            title,
            value=value,
            height=height,
            key=key,
            help=help_text,
            disabled=disabled,
            label_visibility="collapsed",
        )

    def _body():
        e1, e2 = st.columns([1.0, 1.0], gap="small")

        with e1:
            new_list = _editor_block(
                "Methods",
                list_text_current,
                UIConfig.LIST_EDITOR_HEIGHT,
                _key("list_text"),
                "Each non-empty line becomes one item in the report.",
                locked,
            )
        with e2:
            new_narr = _editor_block(
                "Narrative",
                narr_text_current,
                UIConfig.NARR_EDITOR_HEIGHT,
                _key("narr_text"),
                "Write one coherent paragraph (blank lines allowed).",
                locked,
            )

        new_list_norm = "\n".join(_lines(new_list))
        new_narr_norm = _split_paragraphs(new_narr)

        ss[SS_LIST_TEXT] = new_list_norm
        ss[SS_NARR_TEXT] = new_narr_norm

        ss[SS_DCM_DIRTY_LIST] = _split_paragraphs(new_list_norm) != _split_paragraphs("\n".join(auto_list))
        ss[SS_DCM_DIRTY_NARR] = _split_paragraphs(new_narr_norm) != _split_paragraphs(auto_narr)

        w1, c1 = _word_char_count(new_list_norm)
        w2, c2 = _word_char_count(new_narr_norm)
        st.markdown(
            f"<div class='t6-s7-subtle'>Methods: {w1} words · {c1} chars &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"Narrative: {w2} words · {c2} chars</div>",
            unsafe_allow_html=True,
        )

    _card("2) Edit text", _body, help_text="Everything updates immediately. Confirm when final.")

    def _preview_body():
        items = _lines(_s(ss.get(SS_LIST_TEXT))) or auto_list
        _render_methods_preview(items, mode=_s(ss.get(SS_DCM_PREVIEW_MODE)))
        st.markdown("---")
        st.write(_split_paragraphs(_s(ss.get(SS_NARR_TEXT))) or auto_narr)

    _card("Live Preview", _preview_body, help_text="This is close to how it will read in the report.")

    # Keep layout more stable: always allocate a diff container, fill only when enabled
    diff_slot = st.container()
    with diff_slot:
        if bool(ss.get(SS_DCM_SHOW_DIFF, False)):

            def _diff_body():
                diff_list = _simple_diff("\n".join(auto_list), _s(ss.get(SS_LIST_TEXT)))
                diff_narr = _simple_diff(auto_narr, _s(ss.get(SS_NARR_TEXT)))
                with st.expander("Methods diff", expanded=False):
                    st.code(diff_list, language="text")
                with st.expander("Narrative diff", expanded=False):
                    st.code(diff_narr, language="text")

            _card("Diff (Auto → Edited)", _diff_body)


def _controls_tab(ctx: Tool6Context, ovr: Dict[str, Any]) -> None:
    ss = st.session_state

    def _tpl_body():
        opts = list(TEMPLATE_LIBRARY.keys())
        t1, t2, t3 = st.columns([2.2, 1.0, 1.0], gap="small")

        with t1:
            ss[SS_DCM_TEMPLATE] = st.selectbox(
                "Choose a template",
                options=opts,
                index=_safe_index(opts, _s(ss.get(SS_DCM_TEMPLATE)), UIConfig.DEFAULT_TEMPLATE),
                key=_key("tpl_name"),
                help="Templates set style/tone/preview; you can still edit text afterwards.",
            )

        with t2:
            if st.button("Apply Template", use_container_width=True, key=_key("tpl_apply")):
                _apply_template(ss[SS_DCM_TEMPLATE])
                ss[SS_DCM_HASH] = ""

        with t3:
            with st.popover("Details", use_container_width=True):
                tpl = TEMPLATE_LIBRARY.get(ss[SS_DCM_TEMPLATE], {})
                st.write(f"Style: {tpl.get('style')}")
                st.write(f"Tone: {tpl.get('tone')}")
                st.write(f"Preview: {tpl.get('preview')}")

    def _style_body():
        style_opts = ["Short", "Standard", "Detailed"]
        tone_opts = ["Neutral", "Formal", "Action-oriented"]
        prev_opts = ["Numbered", "Bullets"]

        c1, c2, c3 = st.columns([1.2, 1.2, 1.2], gap="small")
        with c1:
            ss[SS_DCM_STYLE] = st.selectbox(
                "Style",
                options=style_opts,
                index=_safe_index(style_opts, _s(ss.get(SS_DCM_STYLE)), UIConfig.DEFAULT_STYLE),
                key=_key("style"),
            )
        with c2:
            ss[SS_DCM_TONE] = st.selectbox(
                "Tone",
                options=tone_opts,
                index=_safe_index(tone_opts, _s(ss.get(SS_DCM_TONE)), UIConfig.DEFAULT_TONE),
                key=_key("tone"),
            )
        with c3:
            ss[SS_DCM_PREVIEW_MODE] = st.selectbox(
                "Preview mode",
                options=prev_opts,
                index=_safe_index(prev_opts, _s(ss.get(SS_DCM_PREVIEW_MODE)), UIConfig.DEFAULT_PREVIEW),
                key=_key("preview_mode"),
            )

        st.caption("Changes apply instantly to the auto draft (unless you have edited/confirmed).")
        ss[SS_DCM_HASH] = ""  # instant regen

        with st.expander("Auto draft (current)", expanded=False):
            al, an = _compute_and_cache_auto_text(ovr)
            st.code("\n".join(al), language="text")
            st.code(an, language="text")

    def _translate_body():
        tr1, tr2, tr3, tr4 = st.columns([1.2, 1.2, 1.4, 1.2], gap="small")
        src_opts = ["Edited", "Auto"]
        tgt_opts = UIConfig.TRANSLATE_TARGETS

        with tr1:
            ss[SS_DCM_TRANSLATE_SOURCE] = st.selectbox(
                "Translate source",
                options=src_opts,
                index=_safe_index(src_opts, _s(ss.get(SS_DCM_TRANSLATE_SOURCE)), "Edited"),
                key=_key("tr_source"),
            )
        with tr2:
            ss[SS_DCM_TRANSLATE_TARGET] = st.selectbox(
                "Target language",
                options=tgt_opts,
                index=_safe_index(tgt_opts, _s(ss.get(SS_DCM_TRANSLATE_TARGET)), "Persian/Dari"),
                key=_key("tr_target"),
            )
        with tr3:
            if st.button("Translate Now", use_container_width=True, key=_key("tr_now")):
                al, an = _compute_and_cache_auto_text(ovr)

                if ss[SS_DCM_TRANSLATE_SOURCE] == "Edited":
                    source_list = _s(ss.get(SS_LIST_TEXT)) or "\n".join(al)
                    source_narr = _s(ss.get(SS_NARR_TEXT)) or an
                else:
                    source_list = "\n".join(al)
                    source_narr = an

                t_list, warn1 = _translate_text(ctx, source_list, _s(ss.get(SS_DCM_TRANSLATE_TARGET)))
                t_narr, warn2 = _translate_text(ctx, source_narr, _s(ss.get(SS_DCM_TRANSLATE_TARGET)))
                warn = warn1 or warn2

                if warn:
                    status_card("Translation not configured", warn, level="warning")
                else:
                    ss[SS_LIST_TEXT] = "\n".join(_lines(t_list))
                    ss[SS_NARR_TEXT] = _split_paragraphs(t_narr)
                    ss[SS_DCM_DIRTY_LIST] = True
                    ss[SS_DCM_DIRTY_NARR] = True
                    ss[SS_CONFIRMED] = False

                    tgt = _s(ss.get(SS_DCM_TRANSLATE_TARGET))
                    gi = ss.get("general_info_overrides", {}) or {}
                    gi[f"D_methods_list_text ({tgt})"] = ss[SS_LIST_TEXT]
                    gi[f"D_methods_narrative_text ({tgt})"] = ss[SS_NARR_TEXT]
                    ss["general_info_overrides"] = gi

        with tr4:
            with st.popover("How to enable", use_container_width=True):
                st.write(
                    "Provide a callable in:\n"
                    "st.session_state['tool6_translate_fn']\n\n"
                    "Signature:\n"
                    "def translate_fn(text: str, target: str) -> str"
                )

    _card("Templates", _tpl_body)
    _card("Draft controls", _style_body)
    _card("Translation", _translate_body)


def _insights_tab(ovr: Dict[str, Any]) -> None:
    ss = st.session_state
    selected_core = [(k, lbl) for k, lbl in FLAGS if bool(ovr.get(k))]
    selected_extra = [(k, lbl) for k, lbl in EXTRA_METHODS if bool(ovr.get(k))]

    def _snap_body():
        c1, c2, c3 = st.columns([1.2, 1.2, 1.2], gap="small")
        c1.metric("Selected inputs", str(len(selected_core) + len(selected_extra)))
        c2.metric("Style", _s(ss.get(SS_DCM_STYLE)) or "—")
        c3.metric("Tone", _s(ss.get(SS_DCM_TONE)) or "—")

        st.markdown("<div class='t6-s7-row'>", unsafe_allow_html=True)
        st.markdown(f"<div class='t6-s7-pill'>Preview: {_s(ss.get(SS_DCM_PREVIEW_MODE)) or UIConfig.DEFAULT_PREVIEW}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='t6-s7-pill'>Confirmed: {'Yes' if ss.get(SS_CONFIRMED) else 'No'}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    _card("Snapshot", _snap_body)

    def _trace_body():
        if not (selected_core or selected_extra):
            st.info("No inputs selected. Auto text will fall back to a generic TPM statement.")
            return
        if selected_core:
            st.markdown("**Core inputs**")
            for _, lbl in selected_core:
                st.markdown(f"- {lbl}")
        if selected_extra:
            st.markdown("**Optional modern methods**")
            for _, lbl in selected_extra:
                st.markdown(f"- {lbl}")

    _card("Selected inputs (traceability)", _trace_body)

    def _auto_body():
        al, an = _compute_and_cache_auto_text(ovr)
        with st.expander("Auto methods", expanded=False):
            st.code("\n".join(al), language="text")
        with st.expander("Auto narrative", expanded=False):
            st.code(an, language="text")

    _card("Auto draft (current)", _auto_body)


# =============================================================================
# MAIN
# =============================================================================
def render_step(ctx: Tool6Context) -> bool:
    """
    Step 7: Data Collection Methods (FIXED)
    - Removed @st.fragment to ensure full reruns and correct stepper sync.
    - Added session bridge flags for parent navigation.
    - Reduced layout jumping by injecting CSS once and avoiding manual st.rerun calls.
    """
    _inject_ui_css_once()
    _ensure_state()

    ss = st.session_state
    ovr: Dict[str, Any] = ss.get("general_info_overrides", {}) or {}

    st.markdown("<div class='t6-s7-wrap'>", unsafe_allow_html=True)
    with st.container(border=True):
        _sticky_bar()

        tab_draft, tab_insights, tab_controls = st.tabs(["Draft", "Insights", "Controls"])

        with tab_draft:
            left, right = st.columns([1.05, 1.0], gap="large")
            with left:
                _draft_left_panel(ovr)
            with right:
                _draft_right_panel(ctx, ovr)

        with tab_insights:
            _insights_tab(ovr)

        with tab_controls:
            _controls_tab(ctx, ovr)

        # Final save to overrides
        auto_list, auto_narr = _compute_and_cache_auto_text(ovr)

        final_items = _lines(_s(ss.get(SS_LIST_TEXT))) or auto_list
        final_list_text = "\n".join(final_items)
        final_narr_text = _s(ss.get(SS_NARR_TEXT)) or auto_narr

        ovr["D_methods_list_text"] = final_list_text
        ovr["D_methods_narrative_text"] = final_narr_text
        ss["general_info_overrides"] = ovr

        st.divider()

        # Readiness + feedback
        ready = bool(ss.get(SS_CONFIRMED, False)) and bool(final_items)
        ss[SS_STEP7_READY] = ready

        if bool(ss.get(SS_CONFIRMED, False)) and not bool(final_items):
            status_card("Confirmed but empty", "Methods list is empty. Add at least one method line.", level="warning")
        elif ready:
            status_card("Confirmed", "This section is ready and will be included in the generated DOCX.", level="success")
        else:
            if bool(ss.get(SS_DCM_DIRTY_LIST, False)) or bool(ss.get(SS_DCM_DIRTY_NARR, False)):
                status_card("Edited (not confirmed)", "You edited/translated the text. Please confirm when ready.", level="warning")
            else:
                status_card("Auto draft", "This matches the latest auto-generated version.", level="info")

        card_close()

    st.markdown("</div>", unsafe_allow_html=True)

    # Return value for parent stepper logic
    return ready
