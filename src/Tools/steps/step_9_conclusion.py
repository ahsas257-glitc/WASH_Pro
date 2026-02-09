# src/Tools/steps/step_9_conclusion.py
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card


# =============================================================================
# Session keys (Tool6)
# =============================================================================
SS_PAYLOAD = "tool6_conclusion_payload"   # {conclusion_text, key_points, recommendations_summary}
SS_TXT = "tool6_conclusion_text"
SS_RECO = "tool6_conclusion_reco"
SS_KP = "tool6_conclusion_kp"            # list[str]

# UX / automation
SS_LOCK = "tool6_conclusion_approved"    # bool (lock final)
SS_DIRTY = "tool6_conclusion_dirty"      # bool: user edited
SS_FP = "tool6_conclusion_fp"            # fingerprint of upstream data used for auto suggestion

# Translation (API translator hook)
SS_TR_TARGET = "tool6_conclusion_translate_target"  # "English"|"Persian/Dari"
SS_TR_SOURCE = "tool6_conclusion_translate_source"  # "Conclusion"|"Reco"|"All"
SS_TR_LAST_WARN = "tool6_conclusion_translate_warn" # last warning text


# =============================================================================
# Config
# =============================================================================
class UIConfig:
    MOBILE_BREAKPOINT_PX = 900

    HEIGHT_CONCLUSION_DESKTOP = 180
    HEIGHT_CONCLUSION_MOBILE = 160

    HEIGHT_RECO_DESKTOP = 150
    HEIGHT_RECO_MOBILE = 140

    KP_MAX_AUTO = 6
    RECO_MAX_AUTO = 8

    TRANSLATE_TARGETS = ["English", "Persian/Dari"]
    DEFAULT_TRANSLATE_TARGET = "Persian/Dari"


# =============================================================================
# Small helpers
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"t6.s9.{h}"


def _split_lines(text: str) -> List[str]:
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in t.split("\n")]
    return [ln for ln in lines if ln]


def _strip_bullet_prefix(line: str) -> str:
    return re.sub(r"^\s*[-•*]\s*", "", _s(line)).strip()


def bullets_from_text(text: str) -> List[str]:
    """
    Split free text into bullet items:
      - newline-separated
      - lines starting with -, *, •
      - semicolon-separated fallback
    """
    t = _s(text)
    if not t:
        return []

    lines = _split_lines(t)
    if len(lines) > 1:
        out: List[str] = []
        for ln in lines:
            ln = _strip_bullet_prefix(ln)
            if ln:
                out.append(ln)
        return out

    one = lines[0] if lines else t
    if "•" in one:
        return [p.strip() for p in one.split("•") if p.strip()]
    if ";" in one:
        return [p.strip() for p in one.split(";") if p.strip()]
    return []


def _norm_sentence(v: Any) -> str:
    sv = _s(v)
    if not sv:
        return ""
    sv = " ".join(sv.split()).strip().rstrip(" .;:,")
    if not sv:
        return ""
    # Add period if missing
    if sv[-1] not in ".!?":
        sv += "."
    # Gentle capitalization
    if sv and sv[0].isalpha():
        sv = sv[0].upper() + sv[1:]
    return sv


def _clamp_words(text: str, max_words: int) -> str:
    parts = [p for p in re.split(r"\s+", _s(text)) if p]
    if not parts:
        return ""
    if len(parts) <= max_words:
        return " ".join(parts)
    return " ".join(parts[:max_words]).strip()


def _split_paragraphs(text: str) -> str:
    t = (text or "").replace("\r\n", "\n")
    t = "\n".join([ln.rstrip() for ln in t.split("\n")])
    while "\n\n\n" in t:
        t = t.replace("\n\n\n", "\n\n")
    return t.strip()


def _default_conclusion_text() -> str:
    return (
        "Overall, the monitoring confirmed that the assessed WASH intervention is functional and "
        "providing services to the beneficiary community. Addressing the observed technical and "
        "operational gaps through timely corrective actions and strengthened O&M capacity will "
        "improve system reliability and long-term sustainability."
    )


# =============================================================================
# Responsive CSS + sticky bar
# =============================================================================
def _inject_css() -> None:
    st.markdown(
        f"""
<style>
.t6-s9-subtle {{
  opacity: 0.85;
  font-size: 0.92rem;
}}

.t6-s9-sticky {{
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
  .t6-s9-sticky {{
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


def _is_mobile() -> bool:
    # Streamlit doesn't expose viewport width reliably; we approximate via CSS stacking,
    # but for heights we keep a simple heuristic using session hint if set.
    return bool(st.session_state.get("_is_mobile_hint", False))


# =============================================================================
# Upstream extraction (matches your Step3/Step4 structure)
# =============================================================================
def _get_component_observations() -> List[Dict[str, Any]]:
    co = st.session_state.get("tool6_component_observations_final")
    if co is None:
        co = st.session_state.get("component_observations", [])
    return co if isinstance(co, list) else []


def _iter_major_findings(component_observations: List[Dict[str, Any]]) -> List[str]:
    found: List[str] = []
    seen = set()

    def add(txt: Any) -> None:
        t = _s(txt)
        if not t:
            return
        t = " ".join(t.split()).rstrip(" .;:,")
        if not t:
            return
        k = t.lower()
        if k in seen:
            return
        seen.add(k)
        found.append(t)

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
            if isinstance(mt, list):
                for r in mt:
                    if isinstance(r, dict):
                        add(r.get("finding"))
                        if len(found) >= 30:
                            return found
    return found


def _iter_recommendations(component_observations: List[Dict[str, Any]]) -> List[str]:
    recs: List[str] = []
    seen = set()

    def add(txt: Any) -> None:
        t = _s(txt)
        if not t:
            return
        t = " ".join(t.split()).rstrip(" .;:,")
        if not t:
            return
        k = t.lower()
        if k in seen:
            return
        seen.add(k)
        recs.append(t)

    for comp in component_observations or []:
        if not isinstance(comp, dict):
            continue
        ov = comp.get("observations_valid") or []
        if not isinstance(ov, list):
            continue

        for ob in ov:
            if not isinstance(ob, dict):
                continue
            rr = ob.get("recommendations") or []
            if isinstance(rr, list):
                for r in rr:
                    add(r)
                    if len(recs) >= 40:
                        return recs
    return recs


def _auto_key_points(component_observations: List[Dict[str, Any]], max_items: int = UIConfig.KP_MAX_AUTO) -> List[str]:
    """
    Smart: take the first distinct findings (trimmed) as key points.
    """
    findings = _iter_major_findings(component_observations)
    out: List[str] = []
    for f in findings:
        t = _clamp_words(f, 16).rstrip(" .;:,")
        if t:
            out.append(t)
        if len(out) >= max_items:
            break
    return out


def _auto_reco_summary(component_observations: List[Dict[str, Any]], max_items: int = UIConfig.RECO_MAX_AUTO) -> str:
    """
    Smart: collect distinct recommendations, compact, join by newline bullets.
    """
    recs = _iter_recommendations(component_observations)
    compact: List[str] = []
    for r in recs:
        t = _clamp_words(r, 18).rstrip(" .;:,")
        if t:
            compact.append(t)
        if len(compact) >= max_items:
            break
    if not compact:
        return ""
    return "\n".join([f"• {x}" for x in compact])


def _upstream_fingerprint(component_observations: List[Dict[str, Any]]) -> str:
    """
    Light fingerprint to detect upstream change.
    """
    pieces: List[str] = []
    for comp in component_observations[:12]:
        if not isinstance(comp, dict):
            continue
        pieces.append(_s(comp.get("component") or comp.get("title") or comp.get("name")))
        ov = comp.get("observations_valid") or []
        if not isinstance(ov, list):
            continue
        for ob in ov[:12]:
            if not isinstance(ob, dict):
                continue
            pieces.append(_s(ob.get("title")))
            mt = ob.get("major_table") or []
            if isinstance(mt, list):
                for r in mt[:8]:
                    if isinstance(r, dict):
                        pieces.append(_s(r.get("finding")))
            recs = ob.get("recommendations") or []
            if isinstance(recs, list):
                pieces.append(f"recs={len([x for x in recs if _s(x)])}")

    blob = "|".join(pieces).encode("utf-8", errors="ignore")
    return hashlib.sha1(blob).hexdigest()[:16]


# =============================================================================
# Translation (API translator hook)
# =============================================================================
def _get_translate_callable(ctx: Tool6Context):
    """
    API Translator best option:
    Provide callable in: st.session_state['tool6_translate_fn']
    Signature: fn(text:str, target:str) -> str
    """
    fn = st.session_state.get("tool6_translate_fn")
    if callable(fn):
        return fn

    # Optional ctx injection
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
            "with signature: (text, target) -> translated_text"
        )

    try:
        out = fn(t, target)
        return _split_paragraphs(out), None
    except Exception as e:
        return t, f"Translation failed: {e}"


# =============================================================================
# State
# =============================================================================
def _ensure_state_defaults() -> None:
    ss = st.session_state

    ss.setdefault(SS_PAYLOAD, {})
    payload = ss.get(SS_PAYLOAD) or {}
    if not isinstance(payload, dict):
        payload = {}

    payload.setdefault("conclusion_text", _default_conclusion_text())
    payload.setdefault("key_points", [])
    payload.setdefault("recommendations_summary", "")

    ss[SS_PAYLOAD] = payload

    ss.setdefault(SS_TXT, payload.get("conclusion_text", _default_conclusion_text()))
    ss.setdefault(SS_RECO, payload.get("recommendations_summary", ""))

    if SS_KP not in ss:
        kp = payload.get("key_points") or []
        ss[SS_KP] = list(kp) if isinstance(kp, list) else []

    ss.setdefault(SS_LOCK, False)
    if not isinstance(ss.get(SS_LOCK), bool):
        ss[SS_LOCK] = False

    ss.setdefault(SS_DIRTY, False)
    if not isinstance(ss.get(SS_DIRTY), bool):
        ss[SS_DIRTY] = False

    ss.setdefault(SS_FP, "")

    ss.setdefault(SS_TR_TARGET, UIConfig.DEFAULT_TRANSLATE_TARGET)
    if ss[SS_TR_TARGET] not in UIConfig.TRANSLATE_TARGETS:
        ss[SS_TR_TARGET] = UIConfig.DEFAULT_TRANSLATE_TARGET

    ss.setdefault(SS_TR_SOURCE, "All")
    if ss[SS_TR_SOURCE] not in ("Conclusion", "Reco", "All"):
        ss[SS_TR_SOURCE] = "All"

    ss.setdefault(SS_TR_LAST_WARN, "")


def _commit_payload() -> None:
    ss = st.session_state
    kp: List[str] = ss.get(SS_KP) or []
    if not isinstance(kp, list):
        kp = []

    ss[SS_PAYLOAD] = {
        "conclusion_text": _split_paragraphs(_s(ss.get(SS_TXT))) or _default_conclusion_text(),
        "key_points": [_strip_bullet_prefix(_s(x)) for x in kp if _s(x)],
        "recommendations_summary": _s(ss.get(SS_RECO)),
    }


def _recompute_dirty(auto_txt: str, auto_kp: List[str], auto_reco: str) -> None:
    """
    Dirty if current differs from auto snapshot.
    """
    ss = st.session_state

    cur_txt = _split_paragraphs(_s(ss.get(SS_TXT)))
    cur_reco = _s(ss.get(SS_RECO))
    cur_kp = ss.get(SS_KP) or []
    if not isinstance(cur_kp, list):
        cur_kp = []

    auto_txt_n = _split_paragraphs(auto_txt)
    auto_reco_n = _s(auto_reco)

    # normalize KP
    auto_kp_n = [_strip_bullet_prefix(_s(x)) for x in (auto_kp or []) if _s(x)]
    cur_kp_n = [_strip_bullet_prefix(_s(x)) for x in cur_kp if _s(x)]

    ss[SS_DIRTY] = (cur_txt != auto_txt_n) or (cur_reco != auto_reco_n) or (cur_kp_n != auto_kp_n)


# =============================================================================
# UI components
# =============================================================================
def _kp_editor_fast() -> None:
    """
    Fast key points editor:
    - single textarea (one per line)
    """
    ss = st.session_state
    kp_list: List[str] = ss.get(SS_KP) or []
    if not isinstance(kp_list, list):
        kp_list = []

    raw = "\n".join([_strip_bullet_prefix(_s(x)) for x in kp_list if _s(x)])
    new_raw = st.text_area(
        "Key points (one per line)",
        value=raw,
        height=120,
        key=_key("kp_textarea"),
        placeholder="• Key point 1\n• Key point 2\n• Key point 3",
        label_visibility="collapsed",
    )

    new_list: List[str] = []
    for ln in (new_raw or "").splitlines():
        ln = _strip_bullet_prefix(ln)
        if ln:
            new_list.append(ln)

    ss[SS_KP] = new_list


def _preview_panel() -> None:
    ss = st.session_state
    payload = ss.get(SS_PAYLOAD) or {}

    preview_text = _s(payload.get("conclusion_text")) or _default_conclusion_text()
    preview_kp = payload.get("key_points") or []
    preview_reco = _s(payload.get("recommendations_summary"))

    with st.container(border=True):
        st.markdown("**Conclusion paragraph**")
        st.write(preview_text)

    if isinstance(preview_kp, list) and any(_s(x) for x in preview_kp):
        with st.container(border=True):
            st.markdown("**Key points**")
            for it in preview_kp:
                if _s(it):
                    st.write(f"• {_s(it)}")

    if preview_reco:
        items = bullets_from_text(preview_reco)
        with st.container(border=True):
            st.markdown("**Recommendations summary**")
            if items:
                for it in items:
                    st.write(f"• {it}")
            else:
                st.write(preview_reco)


# =============================================================================
# MAIN
# =============================================================================
def render_step(ctx: Tool6Context) -> bool:
    """
    Step 9 — Conclusion (Advanced + Responsive + Sticky Actions + Dirty State + Translate)
    Stores:
      st.session_state["tool6_conclusion_payload"] = {
          "conclusion_text": str,
          "key_points": [str, ...],
          "recommendations_summary": str
      }
    """
    _inject_css()
    _ensure_state_defaults()

    component_observations = _get_component_observations()
    fp = _upstream_fingerprint(component_observations)

    # Auto suggestions (do not overwrite user if dirty/approved)
    auto_txt = _default_conclusion_text()
    auto_kp = _auto_key_points(component_observations)
    auto_reco = _auto_reco_summary(component_observations)

    # If upstream changed and user NOT dirty and NOT approved => refresh editor softly
    ss = st.session_state
    if ss.get(SS_FP) != fp:
        ss[SS_FP] = fp
        if (not bool(ss.get(SS_DIRTY))) and (not bool(ss.get(SS_LOCK))):
            # only fill if empty-ish
            if not _s(ss.get(SS_TXT)):
                ss[SS_TXT] = auto_txt
            if not (ss.get(SS_KP) or []):
                ss[SS_KP] = auto_kp
            if not _s(ss.get(SS_RECO)):
                ss[SS_RECO] = auto_reco

    with st.container(border=True):

        # ---------------- Sticky action bar ----------------
        st.markdown('<div class="t6-s9-sticky">', unsafe_allow_html=True)
        a1, a2, a3, a4, a5 = st.columns([1.15, 1.15, 1.15, 1.35, 1.20], gap="small")

        with a1:
            if st.button("✨ Auto-fill", use_container_width=True, key=_key("autofill")):
                ss[SS_TXT] = auto_txt
                ss[SS_KP] = auto_kp
                ss[SS_RECO] = auto_reco
                ss[SS_DIRTY] = False
                ss[SS_LOCK] = False
                _commit_payload()
                status_card("Auto-filled", "Draft generated from findings and recommendations.", level="success")

        with a2:
            if st.button("↺ Reset", use_container_width=True, key=_key("reset")):
                ss[SS_TXT] = _default_conclusion_text()
                ss[SS_KP] = []
                ss[SS_RECO] = ""
                ss[SS_DIRTY] = False
                ss[SS_LOCK] = False
                _commit_payload()
                status_card("Reset", "Reset to default text.", level="info")

        with a3:
            if st.button("💾 Save", use_container_width=True, key=_key("save")):
                _commit_payload()
                status_card("Saved", "Conclusion saved to session payload.", level="success")

        with a4:
            # translate (quick access)
            ss[SS_TR_TARGET] = st.selectbox(
                "Translate to",
                options=UIConfig.TRANSLATE_TARGETS,
                index=UIConfig.TRANSLATE_TARGETS.index(_s(ss.get(SS_TR_TARGET)) or UIConfig.DEFAULT_TRANSLATE_TARGET),
                key=_key("tr_target"),
                label_visibility="collapsed",
            )

        with a5:
            ss[SS_LOCK] = st.toggle(
                "Approved",
                value=bool(ss.get(SS_LOCK, False)),
                key=_key("approved"),
                help="When approved, auto-fill will not overwrite your final text.",
            )
        st.markdown("</div>", unsafe_allow_html=True)

        # ---------------- Tabs (reduce scrolling) ----------------
        tab_draft, tab_insights, tab_controls = st.tabs(["Draft", "Insights", "Controls"])

        # ======================================================
        # Draft tab
        # ======================================================
        with tab_draft:
            left, right = st.columns([0.58, 0.42], gap="large")

            with left:
                h_txt = UIConfig.HEIGHT_CONCLUSION_MOBILE if _is_mobile() else UIConfig.HEIGHT_CONCLUSION_DESKTOP
                h_reco = UIConfig.HEIGHT_RECO_MOBILE if _is_mobile() else UIConfig.HEIGHT_RECO_DESKTOP

                st.markdown("### Main conclusion text")
                st.text_area(
                    "Conclusion text",
                    key=SS_TXT,
                    height=h_txt,
                    label_visibility="collapsed",
                    placeholder="Write your conclusion paragraph here...",
                    disabled=bool(ss.get(SS_LOCK)),
                )

                st.markdown("### Key points (optional)")
                _kp_editor_fast()

                st.markdown("### Recommendations summary (optional)")
                st.text_area(
                    "Recommendations summary",
                    key=SS_RECO,
                    height=h_reco,
                    label_visibility="collapsed",
                    placeholder="Paste bullets / lines / semicolon-separated recommendations...",
                    disabled=bool(ss.get(SS_LOCK)),
                )

                # Commit + dirty
                _commit_payload()
                _recompute_dirty(auto_txt, auto_kp, auto_reco)

                # counters
                txt = _split_paragraphs(_s(ss.get(SS_TXT)))
                kp_count = len([x for x in (ss.get(SS_KP) or []) if _s(x)])
                reco_items = bullets_from_text(_s(ss.get(SS_RECO)))
                words = len([w for w in re.split(r"\s+", txt) if w.strip()]) if txt else 0

                st.markdown(
                    f"<div class='t6-s9-subtle'>Words: {words} · Key points: {kp_count} · Reco items: {len(reco_items) if reco_items else 0}</div>",
                    unsafe_allow_html=True,
                )

                # status
                if ss.get(SS_LOCK):
                    status_card("Approved", "This content is locked and will be used in DOCX.", level="success")



            with right:
                st.markdown("### Live preview (DOCX content)")
                _preview_panel()
                st.caption("✅ Stored in: st.session_state['tool6_conclusion_payload']")

        # ======================================================
        # Insights tab
        # ======================================================
        with tab_insights:
            findings = _iter_major_findings(component_observations)
            recs = _iter_recommendations(component_observations)

            c1, c2, c3 = st.columns([1.2, 1.2, 1.2], gap="small")
            c1.metric("Detected findings", str(len(findings)))
            c2.metric("Detected recommendations", str(len(recs)))
            c3.metric("Approved", "Yes" if ss.get(SS_LOCK) else "No")

            st.divider()

            with st.expander("Show top findings (auto source)", expanded=False):
                if findings:
                    for f in findings[:12]:
                        st.write(f"• {f}")
                else:
                    st.info("No findings detected from major_table.")

            with st.expander("Show top recommendations (auto source)", expanded=False):
                if recs:
                    for r in recs[:12]:
                        st.write(f"• {r}")
                else:
                    st.info("No recommendations detected from observations_valid[].recommendations.")

            st.divider()
            st.markdown("**Auto draft preview (what Auto-fill would generate):**")
            with st.container(border=True):
                st.write(_default_conclusion_text())
                akp = _auto_key_points(component_observations)
                if akp:
                    st.write("")
                    st.markdown("**Key points:**")
                    for x in akp:
                        st.write(f"• {x}")
                areco = _auto_reco_summary(component_observations)
                if areco:
                    st.write("")
                    st.markdown("**Recommendations:**")
                    for x in bullets_from_text(areco):
                        st.write(f"• {x}")

        # ======================================================
        # Controls tab (Translate + quick actions)
        # ======================================================
        with tab_controls:
            st.markdown("### Translation (one-click)")

            t1, t2, t3, t4 = st.columns([1.2, 1.2, 1.25, 1.35], gap="small")

            with t1:
                ss[SS_TR_SOURCE] = st.selectbox(
                    "Translate scope",
                    options=["Conclusion", "Reco", "All"],
                    index=["Conclusion", "Reco", "All"].index(_s(ss.get(SS_TR_SOURCE)) or "All"),
                    key=_key("tr_source"),
                    help="Choose which fields to translate.",
                )

            with t2:
                ss[SS_TR_TARGET] = st.selectbox(
                    "Target language",
                    options=UIConfig.TRANSLATE_TARGETS,
                    index=UIConfig.TRANSLATE_TARGETS.index(_s(ss.get(SS_TR_TARGET)) or UIConfig.DEFAULT_TRANSLATE_TARGET),
                    key=_key("tr_target_2"),
                )

            with t3:
                if st.button("Translate Now", use_container_width=True, key=_key("tr_now")):
                    warn_all: List[str] = []
                    changed = False

                    if ss.get(SS_TR_SOURCE) in ("Conclusion", "All"):
                        translated, warn = _translate_text(ctx, _s(ss.get(SS_TXT)), _s(ss.get(SS_TR_TARGET)))
                        if warn:
                            warn_all.append(warn)
                        else:
                            ss[SS_TXT] = translated
                            changed = True

                    if ss.get(SS_TR_SOURCE) in ("Reco", "All"):
                        translated, warn = _translate_text(ctx, _s(ss.get(SS_RECO)), _s(ss.get(SS_TR_TARGET)))
                        if warn:
                            warn_all.append(warn)
                        else:
                            ss[SS_RECO] = translated
                            changed = True

                    if warn_all:
                        ss[SS_TR_LAST_WARN] = "\n".join(sorted(set(warn_all)))
                        status_card("Translation not configured", ss[SS_TR_LAST_WARN], level="warning")
                    else:
                        ss[SS_TR_LAST_WARN] = ""
                        if changed:
                            ss[SS_DIRTY] = True
                            ss[SS_LOCK] = False
                            _commit_payload()
                            # store bilingual variants (optional)
                            payload = ss.get(SS_PAYLOAD) or {}
                            payload[f"conclusion_text__{ss[SS_TR_TARGET]}"] = _s(ss.get(SS_TXT))
                            payload[f"recommendations_summary__{ss[SS_TR_TARGET]}"] = _s(ss.get(SS_RECO))
                            ss[SS_PAYLOAD] = payload
                            status_card("Translated", "Translation applied. Please review then approve.", level="success")

            with t4:
                with st.popover("How to enable API translator", use_container_width=True):
                    st.write(
                        "✅ Best option: API translator\n\n"
                        "Register a callable in:\n"
                        "st.session_state['tool6_translate_fn']\n\n"
                        "Signature:\n"
                        "def translate_fn(text: str, target: str) -> str\n\n"
                        "Then the Translate button works instantly."
                    )

            if _s(ss.get(SS_TR_LAST_WARN)):
                st.warning(_s(ss.get(SS_TR_LAST_WARN)))

            st.divider()
            st.markdown("### Quick actions")
            q1, q2, q3 = st.columns([1.1, 1.1, 1.8], gap="small")
            with q1:
                if st.button("Normalize punctuation", use_container_width=True, key=_key("norm")):
                    ss[SS_TXT] = _split_paragraphs(_norm_sentence(_s(ss.get(SS_TXT))).rstrip(".") + ".")
                    # normalize reco lines
                    reco_items = bullets_from_text(_s(ss.get(SS_RECO)))
                    if reco_items:
                        ss[SS_RECO] = "\n".join([f"• {_norm_sentence(x).rstrip('.')}" for x in reco_items]).strip()
                    ss[SS_DIRTY] = True
                    ss[SS_LOCK] = False
                    _commit_payload()
                    status_card("Normalized", "Text cleaned and standardized.", level="success")

            with q2:
                if st.button("Approve & lock", use_container_width=True, key=_key("approve_lock")):
                    ss[SS_LOCK] = True
                    _commit_payload()
                    status_card("Approved", "Locked for DOCX output.", level="success")


        # Final validation hint
        final_txt = _split_paragraphs(_s(ss.get(SS_TXT)))
        if not final_txt:
            status_card("Empty text", "Conclusion text is empty. Default will be used in DOCX.", level="warning")
        else:
            status_card("Ready", "Conclusion payload is ready for DOCX generation.", level="success")

        card_close()

    # Safe: builder already has fallbacks; always allow Next
    return True
