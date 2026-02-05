# src/Tools/steps/step_10_generate_report.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import hashlib

import streamlit as st

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card


# =============================================================================
# Helpers
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _get_component_observations() -> List[Dict[str, Any]]:
    """
    Source of truth after Step 4 merge:
      st.session_state["tool6_component_observations_final"]
    Fallback: "component_observations"
    """
    obs = st.session_state.get("tool6_component_observations_final")
    if obs is None:
        obs = st.session_state.get("component_observations", [])
    return obs if isinstance(obs, list) else []


def _preview_general_info(overrides: Dict[str, Any]) -> None:
    items = [(k, _s(v)) for k, v in (overrides or {}).items() if _s(k)]
    if not items:
        st.info("No General Info overrides found.")
        return

    left, right = st.columns(2, gap="large")
    half = (len(items) + 1) // 2
    for idx, (k, v) in enumerate(items):
        target = left if idx < half else right
        with target:
            st.markdown(f"**{k}**")
            st.write(v or "—")


def _extract_summary_findings(component_observations: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """
    Correct extraction for your project:
      components -> observations_valid -> major_table rows (finding + Tools) + recommendations list
    """
    out: List[Tuple[str, str]] = []

    for comp in component_observations or []:
        if not isinstance(comp, dict):
            continue
        ov = comp.get("observations_valid") or []
        if not isinstance(ov, list):
            continue

        for ob in ov:
            if not isinstance(ob, dict):
                continue

            # A) Major table findings (Step 4)
            mt = ob.get("major_table") or []
            if isinstance(mt, list):
                for r in mt:
                    if not isinstance(r, dict):
                        continue
                    finding = _s(r.get("finding"))
                    tools = _s(r.get("Tools"))
                    if finding:
                        reco = f"Tools: {tools}" if tools else "—"
                        out.append((finding, reco))

            # B) Recommendations (Step 4) - put as separate lines if no major_table
            recs = ob.get("recommendations") or []
            if isinstance(recs, list) and recs:
                # keep it short; attach as “Recommendation: ...”
                for rr in recs:
                    rr_s = _s(rr)
                    if rr_s:
                        out.append(("Recommendation", rr_s))

    return out


def _preview_findings_table(component_observations: List[Dict[str, Any]]) -> None:
    extracted = _extract_summary_findings(component_observations)

    if not extracted:
        st.info("No findings captured yet to preview.")
        return

    # Fast markdown table
    lines = []
    lines.append("| No. | Finding | Recommendation / Notes |")
    lines.append("|---:|---|---|")
    for i, (f, r) in enumerate(extracted, start=1):
        ff = _s(f).replace("\n", " ")
        rr = (_s(r) or "—").replace("\n", " ")
        lines.append(f"| {i} | {ff} | {rr} |")

    st.markdown("\n".join(lines))


def _preview_conclusion(conclusion_payload: Dict[str, Any]) -> None:
    txt = _s(conclusion_payload.get("conclusion_text"))
    kp = conclusion_payload.get("key_points") or []
    reco = _s(conclusion_payload.get("recommendations_summary"))

    st.markdown("### Conclusion")
    st.write(txt or "—")

    if isinstance(kp, list) and any(_s(x) for x in kp):
        st.markdown("**Key Points**")
        for it in kp:
            if _s(it):
                st.write(f"• {_s(it)}")

    if reco:
        st.markdown("**Recommendations Summary**")
        st.write(reco)


def _readiness_flags(ctx: Tool6Context, *, cover_bytes: Optional[bytes]) -> Dict[str, bool]:
    # Step 2
    gi_ok = bool(st.session_state.get("general_info_overrides"))
    # Step 3/4 merged data
    obs_ok = bool(_get_component_observations())
    # Step 6 saved into overrides by your Step 6 file
    gi = st.session_state.get("general_info_overrides", {}) or {}
    exec_ok = bool(_s(gi.get("Executive Summary Text")))
    # Step 7 saved into overrides
    dcm_ok = bool(_s(gi.get("D_methods_list_text"))) and bool(_s(gi.get("D_methods_narrative_text")))
    # Step 9 saved payload
    conclusion_ok = bool(st.session_state.get("tool6_conclusion_payload"))

    return {
        "Cover Photo": bool(cover_bytes),
        "General Info": gi_ok,
        "Observations / Findings": obs_ok,
        "Executive Summary": exec_ok,
        "Data Collection Methods": dcm_ok,
        "Conclusion": conclusion_ok,
    }


# =============================================================================
# MAIN
# =============================================================================
def render_step(
    ctx: Tool6Context,
    *,
    resolve_cover_bytes,
    on_generate_docx,
) -> bool:
    """
    Step 10: Generate Report (Preview + Download)
    - Fast preview from session_state payloads
    - Generate DOCX only when user confirms
    """
    st.subheader("Step 10 — Generate Report")
    st.caption("Preview sections quickly. When ready, generate the final Word file.")

    gi_overrides: Dict[str, Any] = st.session_state.get("general_info_overrides", {}) or {}
    component_observations = _get_component_observations()
    conclusion_payload = st.session_state.get("tool6_conclusion_payload", {}) or {}

    cover_bytes = resolve_cover_bytes()

    # Lightweight preview signature (avoid hashing huge dicts)
    sig = _sha1(
        "|".join(
            [
                str(bool(cover_bytes)),
                str(len(gi_overrides)),
                str(len(component_observations)),
                _s(conclusion_payload.get("conclusion_text"))[:120],
                _s(gi_overrides.get("Executive Summary Text"))[:120],
                _s(gi_overrides.get("D_methods_list_text"))[:120],
            ]
        )
    )

    flags = _readiness_flags(ctx, cover_bytes=cover_bytes)
    ok_count = sum(1 for v in flags.values() if v)
    total = len(flags)

    with st.container(border=True):
        c1, c2, c3 = st.columns([0.45, 0.35, 0.20], vertical_alignment="center")
        with c1:
            st.markdown("### Readiness")
            st.caption("Quick check that everything needed for a clean DOCX exists.")
        with c2:
            st.progress(ok_count / max(1, total))
            st.caption(f"{ok_count}/{total} sections ready")
        with c3:
            st.markdown("### Preview ID")
            st.code(sig, language="text")

        cols = st.columns(3)
        items = list(flags.items())
        for i, (name, ok) in enumerate(items):
            with cols[i % 3]:
                st.write(("✅ " if ok else "⚠️ ") + name)

    st.divider()

    tab1, tab2, tab3 = st.tabs(["📄 Full Preview", "🔎 Sections", "⚙️ Generate & Download"])

    # -----------------------------------------
    # Full preview
    # -----------------------------------------
    with tab1:
        st.markdown("## Cover")
        if cover_bytes:
            st.image(cover_bytes, caption="Cover photo", use_container_width=True)
        else:
            st.warning("Cover photo is missing. DOCX generation will fail until you select it in Step 1.")

        st.divider()

        st.markdown("## General Information")
        _preview_general_info(gi_overrides)

        st.divider()

        st.markdown("## Summary of Findings (preview)")
        _preview_findings_table(component_observations)

        st.divider()

        st.markdown("## Executive Summary (preview)")
        exec_txt = _s(gi_overrides.get("Executive Summary Text"))
        if exec_txt:
            st.write(exec_txt)
        else:
            st.info("Executive Summary text not found. (Step 6 should save it into General Info overrides.)")

        st.divider()

        st.markdown("## Data Collection Methods (preview)")
        d_list = _s(gi_overrides.get("D_methods_list_text"))
        d_narr = _s(gi_overrides.get("D_methods_narrative_text"))
        if d_list:
            items = [ln.strip() for ln in d_list.splitlines() if ln.strip()]
            for i, it in enumerate(items, start=1):
                st.write(f"{i}. {it}")
        if d_narr:
            st.write(d_narr)
        if (not d_list) and (not d_narr):
            st.info("Data Collection Methods not found. (Step 7 should save it into General Info overrides.)")

        st.divider()

        _preview_conclusion(conclusion_payload)

    # -----------------------------------------
    # Sections picker
    # -----------------------------------------
    with tab2:
        pick = st.selectbox(
            "Section",
            [
                "General Information",
                "Summary of Findings",
                "Executive Summary",
                "Data Collection Methods",
                "Conclusion",
            ],
            label_visibility="collapsed",
        )

        if pick == "General Information":
            _preview_general_info(gi_overrides)
        elif pick == "Summary of Findings":
            _preview_findings_table(component_observations)
        elif pick == "Executive Summary":
            exec_txt = _s(gi_overrides.get("Executive Summary Text"))
            if exec_txt:
                st.write(exec_txt)
            else:
                st.info("No Executive Summary text found.")
        elif pick == "Data Collection Methods":
            d_list = _s(gi_overrides.get("D_methods_list_text"))
            d_narr = _s(gi_overrides.get("D_methods_narrative_text"))
            if d_list:
                for i, it in enumerate([ln.strip() for ln in d_list.splitlines() if ln.strip()], start=1):
                    st.write(f"{i}. {it}")
            if d_narr:
                st.write(d_narr)
            if (not d_list) and (not d_narr):
                st.info("No Data Collection Methods found.")
        elif pick == "Conclusion":
            _preview_conclusion(conclusion_payload)

    # -----------------------------------------
    # Generate & download
    # -----------------------------------------
    with tab3:
        st.markdown("### Generate final Word document")
        st.caption("This builds the DOCX. After generation, a download button will appear.")

        if not cover_bytes:
            st.error("Cover photo is missing. Please complete Step 1 first.")
            return True

        confirm = st.checkbox(
            "I reviewed the preview and confirm it is ready for final generation.",
            value=False,
            key="t6.s10.confirm",
        )

        c1, c2 = st.columns([0.62, 0.38], vertical_alignment="center")
        with c1:
            st.write("Click generate to build the DOCX and store it in session for fast download.")
        with c2:
            clicked = st.button(
                "🚀 Generate DOCX",
                use_container_width=True,
                disabled=not confirm,
                key="t6.s10.generate",
            )

        if clicked:
            with st.spinner("Generating DOCX..."):
                ok = bool(on_generate_docx())
            if ok:
                status_card("Generated", "DOCX generated successfully. Download below.", level="success")
            else:
                status_card("Failed", "DOCX generation failed. Re-check missing sections.", level="error")

        # IMPORTANT: your Tool_6.py stores this key:
        bts = st.session_state.get("tool6_docx_bytes")
        if bts:
            st.download_button(
                "⬇️ Download Word (DOCX)",
                data=bts,
                file_name=f"Tool6_Report_{ctx.tpm_id}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key="t6.s10.download",
            )
        else:
            st.info("No DOCX generated yet.")

    return True
