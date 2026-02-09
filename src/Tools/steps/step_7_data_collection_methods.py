# src/Tools/steps/step_7_data_collection_methods.py
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from src.Tools.utils.types import Tool6Context
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

# Controls (like Step 6)
SS_DCM_STYLE = "tool6_dcm_style"          # "Short"|"Standard"|"Detailed"
SS_DCM_TONE = "tool6_dcm_tone"            # "Neutral"|"Formal"|"Action-oriented"
SS_DCM_PREVIEW_MODE = "tool6_dcm_preview_mode"  # "Numbered"|"Bullets"
SS_DCM_TEMPLATE = "tool6_dcm_template"    # template name

# Translation (one-click, pluggable)
SS_DCM_TRANSLATE_TARGET = "tool6_dcm_translate_target"  # "English"|"Persian/Dari"
SS_DCM_TRANSLATE_SOURCE = "tool6_dcm_translate_source"  # "Edited"|"Auto"


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
# UI config
# =============================================================================
class UIConfig:
    # Responsive behavior
    MOBILE_BREAKPOINT_PX = 900

    # Editor sizes
    LIST_EDITOR_HEIGHT = 180
    NARR_EDITOR_HEIGHT = 260

    # Defaults
    DEFAULT_STYLE = "Standard"
    DEFAULT_TONE = "Neutral"
    DEFAULT_PREVIEW = "Numbered"
    DEFAULT_TEMPLATE = "Standard TPM (Balanced)"

    # Translation targets
    TRANSLATE_TARGETS = ["English", "Persian/Dari"]


# =============================================================================
# Template library (like Step 6)
# =============================================================================
TEMPLATE_LIBRARY: Dict[str, Dict[str, Any]] = {
    "Standard TPM (Balanced)": {
        "style": "Standard",
        "tone": "Neutral",
        "preview": "Numbered",
    },
    "Compact (Short + Bullets)": {
        "style": "Short",
        "tone": "Neutral",
        "preview": "Bullets",
    },
    "Donor/Stakeholder (Formal + Detailed)": {
        "style": "Detailed",
        "tone": "Formal",
        "preview": "Numbered",
    },
    "Action Follow-up (Action-oriented)": {
        "style": "Standard",
        "tone": "Action-oriented",
        "preview": "Numbered",
    },
}


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
# UI styling (STANDARD + ALIGNED)
# =============================================================================
def _inject_standard_css() -> None:
    st.markdown(
        f"""
<style>
  [data-testid="stVerticalBlock"] {{ gap: 0.70rem; }}

  /* Global input alignment */
  div[data-testid="stTextInput"] input,
  div[data-testid="stTextArea"] textarea,
  div[data-testid="stSelectbox"] div[role="combobox"],
  div[data-testid="stNumberInput"] input {{
    width: 100% !important;
  }}

  /* Consistent card */
  .t6-card {{
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 14px;
    padding: 14px;
    background: rgba(255,255,255,0.02);
    margin: 0.25rem 0 0.75rem 0;
  }}

  .t6-card-title {{
    font-weight: 700;
    font-size: 0.98rem;
    margin-bottom: 0.35rem;
  }}

  .t6-subtle {{
    opacity: 0.84;
    font-size: 0.92rem;
  }}

  /* Sticky bar */
  .t6-sticky {{
    position: sticky;
    top: 0;
    z-index: 50;
    background: rgba(255,255,255,0.86);
    backdrop-filter: blur(10px);
    padding: 0.65rem 0.75rem;
    border-radius: 14px;
    border: 1px solid rgba(0,0,0,0.06);
    margin-bottom: 0.75rem;
  }}

  @media (prefers-color-scheme: dark) {{
    .t6-sticky {{
      background: rgba(10,10,10,0.62);
      border: 1px solid rgba(255,255,255,0.10);
    }}
    .t6-card {{
      border: 1px solid rgba(255,255,255,0.10);
      background: rgba(255,255,255,0.03);
    }}
  }}

  /* Make columns align nicely (top aligned) */
  div[data-testid="column"] {{
    align-self: flex-start !important;
  }}

  /* Mobile responsiveness */
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
# Translation (pluggable, same pattern as Step 6)
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
            "Register a callable in st.session_state['tool6_translate_fn'] "
            "that accepts (text, target) and returns translated text."
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

    ss.setdefault("general_info_overrides", {})
    ovr = ss["general_info_overrides"]

    for k, _ in FLAGS:
        ovr.setdefault(k, False)

    ss["general_info_overrides"] = ovr


# =============================================================================
# Generation logic (list + dynamic narrative with style/tone)
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
        if style == "Short":
            methods.append("Geo-referenced photos reviewed.")
        else:
            methods.append("Collection and review of geo-referenced photographic evidence to verify physical progress and workmanship.")

    if bool(ovr.get("D0_gps_points_recorded")):
        if style == "Short":
            methods.append("GPS points verified/recorded.")
        else:
            methods.append("Verification of GPS coordinates and location data to confirm site positioning and component alignment.")

    if not methods:
        methods.append(
            "The monitoring visit applied standard Third-Party Monitoring (TPM) data collection techniques in line with UNICEF WASH guidelines."
        )

    return methods


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


def _auto_generate_narrative_dynamic(ovr: Dict[str, Any], style: str, tone: str) -> str:
    style = style or UIConfig.DEFAULT_STYLE
    tb = _tone_bits(tone)

    direct_obs = bool(ovr.get("D0_direct_observation"))
    interviews = bool(ovr.get("D0_key_informant_interview"))
    photos = bool(ovr.get("D0_photos_taken"))
    gps = bool(ovr.get("D0_gps_points_recorded"))

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

    field_bits: List[str] = []
    if direct_obs:
        field_bits.append("Direct on-site technical observation was used to verify workmanship, progress, and functionality.")
    else:
        field_bits.append("Field-based technical observation was limited based on available verification inputs during the visit.")

    if photos:
        field_bits.append("Geo-referenced photographic evidence was collected/reviewed to substantiate observed conditions.")
    else:
        field_bits.append(
            "Photographic evidence was limited; observations relied on available in-person verification and documentation where applicable."
            if style == "Detailed"
            else "Photographic evidence was limited; observations relied on available in-person verification inputs."
        )

    if gps:
        field_bits.append("GPS coordinates were verified/recorded to confirm site positioning and component alignment.")
    else:
        field_bits.append("GPS verification was not emphasized." if style == "Short" else "GPS verification was not emphasized; location confirmation relied on available site references and documentation where applicable.")

    if any_docs:
        doc_phrase = _build_doc_review_phrase(ovr, style=style)
        doc_sentence = doc_phrase if doc_phrase else "Project documentation was reviewed to validate compliance with approved specifications and contractual requirements."
    else:
        doc_sentence = "Documentary evidence was limited during the visit." if style == "Short" else "Documentary evidence was limited; therefore, compliance verification relied more heavily on field observations and stakeholder inputs."

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
        stakeholder_sentence = "Stakeholder engagement was limited." if style == "Short" else "Stakeholder engagement was limited; therefore, reported progress and operational arrangements were verified primarily through field and documentary checks."

    focus = tb["focus"]
    closing = tb["closing"]

    if style == "Short":
        narrative = " ".join([opening, focus, closing])
    else:
        narrative = " ".join([opening, " ".join(field_bits), doc_sentence, stakeholder_sentence, focus, closing])

    return _split_paragraphs(narrative)


def _auto_generate(ovr: Dict[str, Any], style: str, tone: str) -> Tuple[List[str], str]:
    methods = _auto_generate_methods_list(ovr, style=style, tone=tone)
    narrative = _auto_generate_narrative_dynamic(ovr, style=style, tone=tone)
    return methods, narrative


def _fingerprint_core(ovr: Dict[str, Any], style: str, tone: str) -> str:
    parts = [f"{k}={int(bool(ovr.get(k)))}" for k, _ in FLAGS]
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
    val = bool(st.session_state.get(widget_key, False))
    ovr[flag_key] = val


# =============================================================================
# MAIN
# =============================================================================
def render_step(ctx: Tool6Context) -> bool:
    _inject_standard_css()
    _ensure_state()

    ss = st.session_state
    ovr: Dict[str, Any] = ss.get("general_info_overrides", {}) or {}

    with st.container(border=True):
        # =========================================================
        # Sticky actions (standard aligned row)
        # =========================================================
        st.markdown('<div class="t6-sticky">', unsafe_allow_html=True)
        a1, a2, a3, a4, a5 = st.columns([1.15, 1.15, 1.4, 1.2, 1.2], gap="small")

        with a1:
            if st.button("Regenerate", use_container_width=True, key=_key("regen")):
                ss[SS_DCM_HASH] = ""
                ss[SS_DCM_DIRTY_LIST] = False
                ss[SS_DCM_DIRTY_NARR] = False
                ss[SS_CONFIRMED] = False
                _compute_and_cache_auto_text(ovr)
                status_card("Regenerated", "Auto text refreshed from current selections.", level="success")

        with a2:
            if st.button("Reset to Auto", use_container_width=True, key=_key("reset_auto")):
                auto_list, auto_narr = _compute_and_cache_auto_text(ovr)
                ss[SS_LIST_TEXT] = "\n".join(auto_list)
                ss[SS_NARR_TEXT] = auto_narr
                ss[SS_DCM_DIRTY_LIST] = False
                ss[SS_DCM_DIRTY_NARR] = False
                ss[SS_CONFIRMED] = False
                status_card("Reset", "Reverted to the latest auto-generated text.", level="success")

        with a3:
            ss[SS_DCM_SHOW_DIFF] = st.toggle(
                "Show Diff",
                value=bool(ss.get(SS_DCM_SHOW_DIFF, False)),
                key=_key("show_diff"),
                help="Compare edited text vs latest auto text.",
            )

        with a4:
            ss[SS_DCM_SHOW_ONLY_SELECTED] = st.toggle(
                "Show only selected",
                value=bool(ss.get(SS_DCM_SHOW_ONLY_SELECTED, False)),
                key=_key("show_selected"),
                help="Hide unselected toggles to reduce scrolling.",
            )

        with a5:
            ss[SS_CONFIRMED] = st.toggle(
                "Confirmed",
                value=bool(ss.get(SS_CONFIRMED, False)),
                key=_key("confirmed"),
                help="When confirmed, this section is locked and considered final for the DOCX.",
            )
        st.markdown("</div>", unsafe_allow_html=True)

        # =========================================================
        # Tabs
        # =========================================================
        tab_draft, tab_insights, tab_controls = st.tabs(["Draft", "Insights", "Controls"])

        # =========================================================
        # DRAFT TAB
        # =========================================================
        with tab_draft:
            left, right = st.columns([1.05, 1.0], gap="large")

            # ---------------- LEFT: toggles ----------------
            with left:
                st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
                st.markdown("<div class='t6-card-title'>1) Select inputs</div>", unsafe_allow_html=True)

                show_only = bool(ss.get(SS_DCM_SHOW_ONLY_SELECTED, False))

                def _flag_widget_key(flag_key: str) -> str:
                    return _key("flag", flag_key)

                with st.expander("Field methods", expanded=True):
                    for flag_key, label in FLAGS[:4]:
                        wkey = _flag_widget_key(flag_key)
                        if wkey not in ss:
                            ss[wkey] = bool(ovr.get(flag_key, False))
                        if show_only and not bool(ss.get(wkey, False)):
                            continue
                        st.toggle(label, value=bool(ss.get(wkey, False)), key=wkey)
                        _sync_ovr_from_widget_state(ovr, wkey, flag_key)

                with st.expander("Documentary evidence", expanded=True):
                    for flag_key, label in FLAGS[4:]:
                        wkey = _flag_widget_key(flag_key)
                        if wkey not in ss:
                            ss[wkey] = bool(ovr.get(flag_key, False))
                        if show_only and not bool(ss.get(wkey, False)):
                            continue
                        st.toggle(label, value=bool(ss.get(wkey, False)), key=wkey)
                        _sync_ovr_from_widget_state(ovr, wkey, flag_key)

                st.markdown(
                    "<div class='t6-subtle'>Tip: Auto text updates when selections or controls change (unless you edited/confirmed).</div>",
                    unsafe_allow_html=True,
                )
                st.markdown("</div>", unsafe_allow_html=True)

            # ---------------- RIGHT: editor + preview ----------------
            with right:
                auto_list, auto_narr = _compute_and_cache_auto_text(ovr)
                locked = bool(ss.get(SS_CONFIRMED, False))

                list_text_current = _s(ss.get(SS_LIST_TEXT)) or "\n".join(auto_list)
                narr_text_current = _s(ss.get(SS_NARR_TEXT)) or auto_narr

                st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
                st.markdown("<div class='t6-card-title'>2) Preview & edit</div>", unsafe_allow_html=True)

                e1, e2 = st.columns([1.0, 1.0], gap="small")
                with e1:
                    st.markdown("**Methods (Editor)**")
                    new_list = st.text_area(
                        "Methods (one per line)",
                        value=list_text_current,
                        height=UIConfig.LIST_EDITOR_HEIGHT,
                        key=_key("list_text"),
                        help="Each non-empty line becomes one numbered/bulleted item in the report.",
                        disabled=locked,
                    )
                with e2:
                    st.markdown("**Narrative (Editor)**")
                    new_narr = st.text_area(
                        "Narrative paragraph",
                        value=narr_text_current,
                        height=UIConfig.NARR_EDITOR_HEIGHT,
                        key=_key("narr_text"),
                        disabled=locked,
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
                    f"<div class='t6-subtle'>Methods: {w1} words · {c1} chars &nbsp;&nbsp;|&nbsp;&nbsp; "
                    f"Narrative: {w2} words · {c2} chars</div>",
                    unsafe_allow_html=True,
                )

                st.markdown("</div>", unsafe_allow_html=True)

                # Preview card
                st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
                st.markdown("<div class='t6-card-title'>Live Preview (Report-like)</div>", unsafe_allow_html=True)
                items = _lines(new_list_norm) or auto_list
                _render_methods_preview(items, mode=_s(ss.get(SS_DCM_PREVIEW_MODE)))
                st.markdown("---")
                st.write(_split_paragraphs(new_narr_norm) or auto_narr)
                st.markdown("</div>", unsafe_allow_html=True)

                # Diff card (optional)
                if bool(ss.get(SS_DCM_SHOW_DIFF, False)):
                    st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
                    st.markdown("<div class='t6-card-title'>Diff (Auto → Edited)</div>", unsafe_allow_html=True)
                    diff_list = _simple_diff("\n".join(auto_list), new_list_norm)
                    diff_narr = _simple_diff(auto_narr, new_narr_norm)
                    with st.expander("Methods diff", expanded=False):
                        st.code(diff_list, language="text")
                    with st.expander("Narrative diff", expanded=False):
                        st.code(diff_narr, language="text")
                    st.markdown("</div>", unsafe_allow_html=True)

                if locked:
                    status_card("Locked", "This section is confirmed. Turn off Confirmed to edit again.", level="info")

        # =========================================================
        # INSIGHTS TAB (aligned)
        # =========================================================
        with tab_insights:
            st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
            st.markdown("<div class='t6-card-title'>Snapshot</div>", unsafe_allow_html=True)

            selected_flags = [(k, lbl) for k, lbl in FLAGS if bool(ovr.get(k))]
            c1, c2, c3 = st.columns([1.2, 1.2, 1.2], gap="small")
            c1.metric("Selected inputs", str(len(selected_flags)))
            c2.metric("Style", _s(ss.get(SS_DCM_STYLE)) or "—")
            c3.metric("Tone", _s(ss.get(SS_DCM_TONE)) or "—")

            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
            st.markdown("<div class='t6-card-title'>Selected inputs (traceability)</div>", unsafe_allow_html=True)
            if selected_flags:
                for _, lbl in selected_flags:
                    st.markdown(f"- {lbl}")
            else:
                st.info("No inputs selected. Auto text will fall back to a generic TPM statement.")
            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
            st.markdown("<div class='t6-card-title'>Auto draft (current)</div>", unsafe_allow_html=True)
            auto_list, auto_narr = _compute_and_cache_auto_text(ovr)
            with st.expander("Auto methods", expanded=False):
                st.code("\n".join(auto_list), language="text")
            with st.expander("Auto narrative", expanded=False):
                st.code(auto_narr, language="text")
            st.markdown("</div>", unsafe_allow_html=True)

        # =========================================================
        # CONTROLS TAB (aligned + cards)
        # =========================================================
        with tab_controls:
            st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
            st.markdown("<div class='t6-card-title'>Templates</div>", unsafe_allow_html=True)

            t1, t2, t3 = st.columns([2.2, 1.0, 1.0], gap="small")
            with t1:
                tpl_name = st.selectbox(
                    "Choose a template",
                    options=list(TEMPLATE_LIBRARY.keys()),
                    index=list(TEMPLATE_LIBRARY.keys()).index(_s(ss.get(SS_DCM_TEMPLATE)) or UIConfig.DEFAULT_TEMPLATE),
                    key=_key("tpl_name"),
                    help="Templates set style/tone/preview. You can still customize after applying.",
                )
                ss[SS_DCM_TEMPLATE] = tpl_name
            with t2:
                if st.button("Apply Template", use_container_width=True, key=_key("tpl_apply")):
                    _apply_template(ss[SS_DCM_TEMPLATE])
                    _compute_and_cache_auto_text(ovr)
                    ss[SS_LIST_TEXT] = "\n".join(ss.get(SS_DCM_AUTO_LIST, []) or [])
                    ss[SS_NARR_TEXT] = _s(ss.get(SS_DCM_AUTO_NARR))
                    status_card("Template applied", "Draft updated using the selected template.", level="success")
            with t3:
                with st.popover("Details", use_container_width=True):
                    tpl = TEMPLATE_LIBRARY.get(ss[SS_DCM_TEMPLATE], {})
                    st.write(f"Style: {tpl.get('style')}")
                    st.write(f"Tone: {tpl.get('tone')}")
                    st.write(f"Preview: {tpl.get('preview')}")

            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
            st.markdown("<div class='t6-card-title'>Style / Tone / Preview</div>", unsafe_allow_html=True)

            c1, c2, c3 = st.columns([1.2, 1.2, 1.2], gap="small")
            with c1:
                ss[SS_DCM_STYLE] = st.selectbox(
                    "Style",
                    options=["Short", "Standard", "Detailed"],
                    index=["Short", "Standard", "Detailed"].index(_s(ss.get(SS_DCM_STYLE)) or UIConfig.DEFAULT_STYLE),
                    key=_key("style"),
                )
            with c2:
                ss[SS_DCM_TONE] = st.selectbox(
                    "Tone",
                    options=["Neutral", "Formal", "Action-oriented"],
                    index=["Neutral", "Formal", "Action-oriented"].index(_s(ss.get(SS_DCM_TONE)) or UIConfig.DEFAULT_TONE),
                    key=_key("tone"),
                )
            with c3:
                ss[SS_DCM_PREVIEW_MODE] = st.selectbox(
                    "Preview mode",
                    options=["Numbered", "Bullets"],
                    index=["Numbered", "Bullets"].index(_s(ss.get(SS_DCM_PREVIEW_MODE)) or UIConfig.DEFAULT_PREVIEW),
                    key=_key("preview_mode"),
                )

            u1, u2 = st.columns([1.3, 1.0], gap="small")
            with u1:
                if st.button("Update Auto Draft", use_container_width=True, key=_key("apply_controls")):
                    ss[SS_DCM_HASH] = ""
                    _compute_and_cache_auto_text(ovr)
                    status_card("Updated", "Auto draft refreshed using the latest controls.", level="success")
            with u2:
                with st.expander("Preview auto text", expanded=False):
                    al, an = _compute_and_cache_auto_text(ovr)
                    st.code("\n".join(al), language="text")
                    st.code(an, language="text")

            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
            st.markdown("<div class='t6-card-title'>Translation</div>", unsafe_allow_html=True)

            tr1, tr2, tr3, tr4 = st.columns([1.2, 1.2, 1.4, 1.2], gap="small")
            with tr1:
                ss[SS_DCM_TRANSLATE_SOURCE] = st.selectbox(
                    "Translate source",
                    options=["Edited", "Auto"],
                    index=["Edited", "Auto"].index(_s(ss.get(SS_DCM_TRANSLATE_SOURCE)) or "Edited"),
                    key=_key("tr_source"),
                )
            with tr2:
                ss[SS_DCM_TRANSLATE_TARGET] = st.selectbox(
                    "Target language",
                    options=UIConfig.TRANSLATE_TARGETS,
                    index=UIConfig.TRANSLATE_TARGETS.index(_s(ss.get(SS_DCM_TRANSLATE_TARGET)) or "Persian/Dari"),
                    key=_key("tr_target"),
                )
            with tr3:
                if st.button("Translate Now", use_container_width=True, key=_key("tr_now")):
                    auto_list, auto_narr = _compute_and_cache_auto_text(ovr)

                    if ss[SS_DCM_TRANSLATE_SOURCE] == "Edited":
                        source_list = _s(ss.get(SS_LIST_TEXT)) or "\n".join(auto_list)
                        source_narr = _s(ss.get(SS_NARR_TEXT)) or auto_narr
                    else:
                        source_list = "\n".join(auto_list)
                        source_narr = auto_narr

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

                        status_card("Translated", "Translation applied to the editor and saved as a bilingual variant.", level="success")

            with tr4:
                with st.popover("How to enable", use_container_width=True):
                    st.write(
                        "Provide a callable in:\n"
                        "st.session_state['tool6_translate_fn']\n\n"
                        "Signature:\n"
                        "def translate_fn(text: str, target: str) -> str"
                    )

            st.markdown("</div>", unsafe_allow_html=True)

        # =========================================================
        # Final save to overrides + status
        # =========================================================
        auto_list, auto_narr = _compute_and_cache_auto_text(ovr)

        final_items = _lines(_s(ss.get(SS_LIST_TEXT))) or auto_list
        final_list_text = "\n".join(final_items)
        final_narr_text = _s(ss.get(SS_NARR_TEXT)) or auto_narr

        ovr["D_methods_list_text"] = final_list_text
        ovr["D_methods_narrative_text"] = final_narr_text
        ss["general_info_overrides"] = ovr

        st.divider()
        if bool(ss.get(SS_CONFIRMED, False)):
            status_card("Confirmed", "This section will be included in the generated DOCX.", level="success")
        else:
            if bool(ss.get(SS_DCM_DIRTY_LIST, False)) or bool(ss.get(SS_DCM_DIRTY_NARR, False)):
                status_card("Edited (not confirmed)", "You edited/translated the text. Please confirm when ready.", level="warning")
            else:
                status_card("Auto draft", "This matches the latest auto-generated version.", level="info")

        card_close()

    items_final = _lines(_s(ss.get(SS_LIST_TEXT))) or (ss.get(SS_DCM_AUTO_LIST, []) or [])
    return bool(ss.get(SS_CONFIRMED)) and bool(items_final)
