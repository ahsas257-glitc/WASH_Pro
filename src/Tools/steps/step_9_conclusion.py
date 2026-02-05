# src/Tools/steps/step_9_conclusion.py
from __future__ import annotations

import re
from typing import Any, Dict, List

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


# =============================================================================
# Small helpers
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _k(name: str) -> str:
    return f"t6.s9.{name}"


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

    lines = [ln.strip() for ln in t.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [ln for ln in lines if ln]

    if len(lines) > 1:
        out: List[str] = []
        for ln in lines:
            ln = re.sub(r"^\s*[-•*]\s*", "", ln).strip()
            if ln:
                out.append(ln)
        return out

    one = lines[0] if lines else t
    if "•" in one:
        return [p.strip() for p in one.split("•") if p.strip()]
    if ";" in one:
        return [p.strip() for p in one.split(";") if p.strip()]
    return []


def _default_conclusion_text() -> str:
    return (
        "Overall, the monitoring confirmed that the assessed WASH intervention is functional and "
        "providing services to the beneficiary community. Addressing the observed technical and "
        "operational gaps through timely corrective actions and strengthened O&M capacity will "
        "improve system reliability and long-term sustainability."
    )


# =============================================================================
# Smart extraction (matches your Step3/Step4 structure)
# =============================================================================
def _get_component_observations() -> List[Dict[str, Any]]:
    co = st.session_state.get("tool6_component_observations_final")
    if co is None:
        co = st.session_state.get("component_observations", [])
    return co if isinstance(co, list) else []


def _smart_key_points_from_findings(component_observations: List[Dict[str, Any]]) -> List[str]:
    """
    Pull up to 4 distinct findings from:
      component_observations -> observations_valid -> major_table[*].finding
    """
    found: List[str] = []
    seen = set()

    def add(txt: Any) -> None:
        t = _s(txt)
        if not t:
            return
        t = " ".join(t.split()).rstrip(" .;:,")
        if not t:
            return
        norm = t.lower()
        if norm in seen:
            return
        seen.add(norm)
        found.append(t)

    for comp in component_observations:
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
                        if len(found) >= 4:
                            return found[:4]

    return found[:4]


def _smart_reco_summary_from_findings(component_observations: List[Dict[str, Any]]) -> str:
    """
    Collect up to 6 distinct recommendations from:
      observations_valid -> recommendations[list[str]]
    Returns semicolon-separated string.
    """
    recs: List[str] = []
    seen = set()

    def add(txt: Any) -> None:
        t = _s(txt)
        if not t:
            return
        t = " ".join(t.split()).rstrip(" .;:,")
        if not t:
            return
        norm = t.lower()
        if norm in seen:
            return
        seen.add(norm)
        recs.append(t)

    for comp in component_observations:
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
                    if len(recs) >= 6:
                        return "; ".join(recs[:6])

    return "; ".join(recs[:6])


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


def _commit_payload() -> None:
    ss = st.session_state
    kp: List[str] = ss.get(SS_KP) or []
    if not isinstance(kp, list):
        kp = []

    ss[SS_PAYLOAD] = {
        "conclusion_text": _s(ss.get(SS_TXT)) or _default_conclusion_text(),
        "key_points": [_s(x) for x in kp if _s(x)],
        "recommendations_summary": _s(ss.get(SS_RECO)),
    }


# =============================================================================
# UI components
# =============================================================================
def _kp_editor() -> None:
    """
    Fast key points editor:
    - uses a single text_area (one per line) for max speed & simplicity
    """
    ss = st.session_state
    kp_list: List[str] = ss.get(SS_KP) or []
    if not isinstance(kp_list, list):
        kp_list = []

    raw = "\n".join([_s(x) for x in kp_list if _s(x)])
    new_raw = st.text_area(
        "Key points (one per line)",
        value=raw,
        height=120,
        key=_k("kp_textarea"),
        placeholder="• Key point 1\n• Key point 2\n• Key point 3",
        label_visibility="collapsed",
    )

    # Normalize lines
    new_list = []
    for ln in (new_raw or "").splitlines():
        ln = re.sub(r"^\s*[-•*]\s*", "", _s(ln)).strip()
        if ln:
            new_list.append(ln)

    ss[SS_KP] = new_list


# =============================================================================
# MAIN
# =============================================================================
def render_step(ctx: Tool6Context) -> bool:
    """
    Step 9 — Conclusion
    Stores:
      st.session_state["tool6_conclusion_payload"] = {
          "conclusion_text": str,
          "key_points": [str, ...],
          "recommendations_summary": str
      }
    """
    _ = ctx
    _ensure_state_defaults()

    component_observations = _get_component_observations()

    st.subheader("Step 9 — Conclusion")
    st.caption("Edit the conclusion that will be written to the DOCX. Changes are saved in-session.")

    box = st.container(border=True)
    with box:
        card_open(
            "Conclusion",
            subtitle="You can auto-fill from findings/recommendations, then edit and proceed.",
            variant="lg-variant-cyan",
        )

        a1, a2, a3 = st.columns([1, 1, 1], gap="small")
        with a1:
            if st.button("✨ Auto-fill from findings", use_container_width=True, key=_k("autofill")):
                st.session_state[SS_TXT] = _default_conclusion_text()
                st.session_state[SS_KP] = _smart_key_points_from_findings(component_observations)
                st.session_state[SS_RECO] = _smart_reco_summary_from_findings(component_observations)
                _commit_payload()
                status_card("Auto-filled", "Conclusion, key points, and recommendations were generated.", level="success")

        with a2:
            if st.button("↺ Reset", use_container_width=True, key=_k("reset")):
                st.session_state[SS_TXT] = _default_conclusion_text()
                st.session_state[SS_KP] = []
                st.session_state[SS_RECO] = ""
                _commit_payload()
                status_card("Reset", "Reset to defaults.", level="info")

        with a3:
            if st.button("💾 Save now", use_container_width=True, key=_k("save")):
                _commit_payload()
                status_card("Saved", "Conclusion saved.", level="success")

        st.divider()

        left, right = st.columns([0.58, 0.42], gap="large")

        with left:
            st.markdown("### Main conclusion text")
            st.text_area(
                "Conclusion text",
                key=SS_TXT,
                height=160,
                label_visibility="collapsed",
                placeholder="Write your conclusion paragraph here...",
            )

            st.markdown("### Key points (optional)")
            _kp_editor()

            st.markdown("### Recommendations summary (optional)")
            st.text_area(
                "Recommendations summary",
                key=SS_RECO,
                height=120,
                label_visibility="collapsed",
                placeholder="Paste bullets / lines / semicolon-separated recommendations...",
            )

            _commit_payload()

        with right:
            st.markdown("### Live preview (DOCX content)")
            payload = st.session_state.get(SS_PAYLOAD) or {}

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

            st.caption("✅ Stored as: st.session_state['tool6_conclusion_payload']")

        # small validation hint
        if not _s(st.session_state.get(SS_TXT)):
            status_card("Empty text", "Conclusion text is empty. Default will be used in DOCX.", level="warning")
        else:
            status_card("Saved", "Conclusion payload is ready for DOCX generation.", level="success")

        card_close()

    # Always allow Next (safe), since you already handle defaults in builder
    return True
