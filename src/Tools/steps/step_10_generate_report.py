# src/Tools/steps/step_10_generate_report.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import hashlib
import time

import streamlit as st

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card


# =============================================================================
# Session keys
# =============================================================================
SS_GI = "general_info_overrides"
SS_DOCX_BYTES = "tool6_docx_bytes"

SS_CONCLUSION_PAYLOAD = "tool6_conclusion_payload"

# Step 8 preferred outputs (if you use that improved Step 8)
SS_SF_EXTRACTED = "tool6_summary_findings_extracted"  # list[{finding, recommendation}]
SS_SF_SEV_BY_NO = "tool6_severity_by_no"
SS_SF_SEV_BY_FINDING = "tool6_severity_by_finding"
SS_SF_ADD_LEGEND = "tool6_add_legend"

# internal: last generated signature + timestamp
SS_LAST_SIG = "tool6_report_last_sig"
SS_LAST_GEN_TS = "tool6_report_last_generated_ts"


# =============================================================================
# Helpers
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"t6.s10.{h}"


def _inject_css() -> None:
    st.markdown(
        """
<style>
.t6-s10-subtle { opacity: 0.85; font-size: 0.92rem; }

.t6-s10-sticky {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255,255,255,0.75);
  backdrop-filter: blur(8px);
  padding: 0.6rem 0.75rem;
  border-radius: 14px;
  border: 1px solid rgba(0,0,0,0.06);
  margin-bottom: 0.75rem;
}

@media (prefers-color-scheme: dark) {
  .t6-s10-sticky {
    background: rgba(10,10,10,0.55);
    border: 1px solid rgba(255,255,255,0.10);
  }
}

@media (max-width: 900px) {
  div[data-testid="column"] {
    width: 100% !important;
    flex: 1 1 100% !important;
  }
}
</style>
""",
        unsafe_allow_html=True,
    )


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


# =============================================================================
# Preferred preview source for Summary of Findings = Step 8 extracted rows
# =============================================================================
def _get_summary_findings_preview_rows() -> List[Tuple[str, str, str]]:
    """
    Returns list of (finding, severity, recommendation).
    Priority:
      1) Step 8 extracted (user-edited final)
      2) fallback extraction from component_observations (older behavior)
    """
    extracted = st.session_state.get(SS_SF_EXTRACTED) or st.session_state.get("tool6_summary_findings_extracted") or []
    sev_by_no = st.session_state.get(SS_SF_SEV_BY_NO) or {}
    sev_by_finding = st.session_state.get(SS_SF_SEV_BY_FINDING) or {}

    out: List[Tuple[str, str, str]] = []
    if isinstance(extracted, list) and extracted:
        for i, x in enumerate(extracted, start=1):
            if not isinstance(x, dict):
                continue
            f = _s(x.get("finding"))
            r = _s(x.get("recommendation")) or "—"
            if not f:
                continue

            sev = _s(sev_by_no.get(i))
            if not sev:
                # try by finding
                f_norm = f.strip().lower()
                for k, v in (sev_by_finding or {}).items():
                    if _s(k).strip().lower() == f_norm:
                        sev = _s(v)
                        break
            sev = sev or "Medium"

            out.append((f, sev, r))
        return out

    # fallback: older extraction (less accurate vs user-edited Step 8)
    return _fallback_extract_summary_findings(_get_component_observations())


def _fallback_extract_summary_findings(component_observations: List[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    """
    Very lightweight fallback extraction:
      observations_valid -> major_table (finding + recommendation/corrective_action)
    Severity fallback = Medium.
    """
    out: List[Tuple[str, str, str]] = []
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
                    if not isinstance(r, dict):
                        continue
                    finding = _s(r.get("finding"))
                    if not finding:
                        continue
                    reco = _s(r.get("recommendation")) or _s(r.get("corrective_action")) or "—"
                    out.append((finding, "Medium", reco))
    return out


def _preview_findings_table() -> None:
    rows = _get_summary_findings_preview_rows()
    if not rows:
        st.info("No findings captured yet to preview.")
        return

    # Modern compact table using markdown (fast). If you want, can be replaced by st.dataframe.
    lines = []
    lines.append("| No. | Finding | Severity | Recommendation / Corrective Action |")
    lines.append("|---:|---|:---:|---|")
    for i, (f, sev, r) in enumerate(rows, start=1):
        ff = _s(f).replace("\n", " ")
        rr = (_s(r) or "—").replace("\n", " ")
        ss = _s(sev) or "Medium"
        lines.append(f"| {i} | {ff} | {ss} | {rr} |")

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


def _readiness_flags(*, cover_bytes: Optional[bytes]) -> Dict[str, bool]:
    gi = st.session_state.get(SS_GI, {}) or {}
    component_observations = _get_component_observations()
    conclusion_payload = st.session_state.get(SS_CONCLUSION_PAYLOAD, {}) or {}

    gi_ok = bool(gi)
    obs_ok = bool(component_observations)

    exec_ok = bool(_s(gi.get("Executive Summary Text")))
    dcm_ok = bool(_s(gi.get("D_methods_list_text"))) and bool(_s(gi.get("D_methods_narrative_text")))
    conclusion_ok = bool(_s(conclusion_payload.get("conclusion_text"))) or bool(conclusion_payload)

    # Step 8 findings preferred
    sf_rows = st.session_state.get(SS_SF_EXTRACTED) or st.session_state.get("tool6_summary_findings_extracted") or []
    findings_ok = bool(sf_rows) or obs_ok

    return {
        "Cover Photo": bool(cover_bytes),
        "General Info": gi_ok,
        "Observations (Step 3/4)": obs_ok,
        "Summary of Findings (Step 8)": findings_ok,
        "Executive Summary (Step 6)": exec_ok,
        "Data Collection Methods (Step 7)": dcm_ok,
        "Conclusion (Step 9)": conclusion_ok,
    }


def _build_preview_signature(*, cover_bytes: Optional[bytes]) -> str:
    gi: Dict[str, Any] = st.session_state.get(SS_GI, {}) or {}
    conclusion_payload = st.session_state.get(SS_CONCLUSION_PAYLOAD, {}) or {}

    # Keep signature lightweight (avoid hashing huge dicts)
    sig = _sha1(
        "|".join(
            [
                str(bool(cover_bytes)),
                str(len(gi)),
                _s(gi.get("Executive Summary Text"))[:120],
                _s(gi.get("D_methods_list_text"))[:120],
                _s(gi.get("D_methods_narrative_text"))[:120],
                _s(conclusion_payload.get("conclusion_text"))[:120],
                # Step 8 findings signature
                str(len(st.session_state.get(SS_SF_EXTRACTED) or st.session_state.get("tool6_summary_findings_extracted") or [])),
            ]
        )
    )
    return sig


def _fmt_ts(ts: Any) -> str:
    try:
        ts = float(ts)
    except Exception:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


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
    Step 10 — Generate Report (Modern + Minimal default UI)
    - No full preview by default
    - Readiness dashboard + Generate flow
    - Preview is available on demand (drawer/expander)
    - Tracks signature to warn if DOCX is stale
    """
    _inject_css()

    st.subheader("Step 10 — Generate Report")
    st.caption("Generate the final Word file. Preview is available only when you need it.")

    gi_overrides: Dict[str, Any] = st.session_state.get(SS_GI, {}) or {}
    conclusion_payload = st.session_state.get(SS_CONCLUSION_PAYLOAD, {}) or {}

    cover_bytes = resolve_cover_bytes()
    flags = _readiness_flags(cover_bytes=cover_bytes)
    ok_count = sum(1 for v in flags.values() if v)
    total = len(flags)

    sig = _build_preview_signature(cover_bytes=cover_bytes)
    last_sig = _s(st.session_state.get(SS_LAST_SIG))
    last_ts = st.session_state.get(SS_LAST_GEN_TS)

    docx_bytes = st.session_state.get(SS_DOCX_BYTES)
    has_docx = bool(docx_bytes)

    stale = bool(has_docx and last_sig and (last_sig != sig))

    # ---------------- Sticky action bar ----------------
    st.markdown('<div class="t6-s10-sticky">', unsafe_allow_html=True)
    a1, a2, a3, a4 = st.columns([1.35, 1.15, 1.10, 1.40], gap="small")

    with a1:
        st.markdown("**Readiness**")
        st.progress(ok_count / max(1, total))
        st.markdown(f"<div class='t6-s10-subtle'>{ok_count}/{total} sections ready</div>", unsafe_allow_html=True)

    with a2:
        st.markdown("**Build signature**")
        st.code(sig, language="text")

    with a3:
        st.markdown("**Last generated**")
        st.markdown(f"<div class='t6-s10-subtle'>{_fmt_ts(last_ts)}</div>", unsafe_allow_html=True)
        if stale:
            st.warning("DOCX is outdated (inputs changed).")

    with a4:
        # Preview toggle on demand
        show_preview = st.toggle(
            "Show Preview",
            value=False,
            key=_key("show_preview"),
            help="Turn on to preview sections. By default preview is hidden for speed.",
        )
    st.markdown("</div>", unsafe_allow_html=True)

    # ---------------- Readiness details ----------------
    with st.container(border=True):
        card_open(
            "Generate & Download",
            subtitle="Ensure required parts exist, then generate the DOCX. Preview is optional.",
            variant="lg-variant-cyan",
        )

        cols = st.columns(3, gap="small")
        items = list(flags.items())
        for i, (name, ok) in enumerate(items):
            with cols[i % 3]:
                st.write(("✅ " if ok else "⚠️ ") + name)

        st.divider()

        # Core guardrails
        if not cover_bytes:
            status_card("Missing cover", "Cover photo is required. Complete Step 1 first.", level="error")
        elif ok_count < total:
            status_card(
                "Not fully ready",
                "Some sections are missing or incomplete. You can still preview and decide, but generation may fail or be incomplete.",
                level="warning",
            )
        else:
            status_card("Ready", "All required sections appear to be available.", level="success")

        st.divider()

        # ---------------- Generate flow ----------------
        g1, g2, g3 = st.columns([1.35, 1.05, 1.60], gap="small")

        with g1:
            confirm = st.checkbox(
                "I confirm the inputs are ready for final generation.",
                value=False,
                key=_key("confirm"),
                help="This prevents accidental generation.",
            )

        with g2:
            clicked = st.button(
                "🚀 Generate DOCX",
                use_container_width=True,
                disabled=(not confirm) or (not bool(cover_bytes)),
                key=_key("generate"),
                type="primary",
            )

        with g3:
            if has_docx and not stale:
                st.success("A fresh DOCX is available for download.")
            elif has_docx and stale:
                st.warning("A DOCX exists, but it’s stale. Re-generate for latest.")
            else:
                st.info("No DOCX generated yet.")

        if clicked:
            with st.spinner("Generating DOCX..."):
                ok = bool(on_generate_docx())
            if ok:
                # Store signature + timestamp (so we can detect stale later)
                st.session_state[SS_LAST_SIG] = sig
                st.session_state[SS_LAST_GEN_TS] = time.time()
                status_card("Generated", "DOCX generated successfully. Download below.", level="success")
            else:
                status_card("Failed", "DOCX generation failed. Check missing inputs and try again.", level="error")

        # Download panel
        docx_bytes = st.session_state.get(SS_DOCX_BYTES)
        if docx_bytes:
            st.download_button(
                "⬇️ Download Word (DOCX)",
                data=docx_bytes,
                file_name=f"Tool6_Report_{ctx.tpm_id}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                key=_key("download"),
            )

        card_close()

    # ---------------- Preview (ON DEMAND only) ----------------
    if show_preview:
        st.divider()
        tab1, tab2 = st.tabs(["🔎 Sections", "📄 Quick Full (optional)"])

        with tab1:
            pick = st.selectbox(
                "Select section to preview",
                [
                    "Cover",
                    "General Information",
                    "Summary of Findings",
                    "Executive Summary",
                    "Data Collection Methods",
                    "Conclusion",
                ],
                label_visibility="collapsed",
                key=_key("pick_section"),
            )

            if pick == "Cover":
                if cover_bytes:
                    st.image(cover_bytes, caption="Cover photo", use_container_width=True)
                else:
                    st.warning("Cover photo is missing.")
            elif pick == "General Information":
                _preview_general_info(gi_overrides)
            elif pick == "Summary of Findings":
                _preview_findings_table()
            elif pick == "Executive Summary":
                exec_txt = _s(gi_overrides.get("Executive Summary Text"))
                if exec_txt:
                    st.write(exec_txt)
                else:
                    st.info("Executive Summary not found (Step 6 should save it in General Info overrides).")
            elif pick == "Data Collection Methods":
                d_list = _s(gi_overrides.get("D_methods_list_text"))
                d_narr = _s(gi_overrides.get("D_methods_narrative_text"))
                if d_list:
                    items = [ln.strip() for ln in d_list.splitlines() if ln.strip()]
                    for i, it in enumerate(items, start=1):
                        st.write(f"{i}. {it}")
                if d_narr:
                    st.write(d_narr)
                if (not d_list) and (not d_narr):
                    st.info("Data Collection Methods not found (Step 7 should save it into overrides).")
            elif pick == "Conclusion":
                _preview_conclusion(conclusion_payload)

        with tab2:
            # Optional full preview (still not default)
            with st.expander("Show full preview", expanded=False):
                st.markdown("## Cover")
                if cover_bytes:
                    st.image(cover_bytes, caption="Cover photo", use_container_width=True)
                else:
                    st.warning("Cover photo is missing.")

                st.divider()
                st.markdown("## General Information")
                _preview_general_info(gi_overrides)

                st.divider()
                st.markdown("## Summary of Findings")
                _preview_findings_table()

                st.divider()
                st.markdown("## Executive Summary")
                exec_txt = _s(gi_overrides.get("Executive Summary Text"))
                st.write(exec_txt or "—")

                st.divider()
                st.markdown("## Data Collection Methods")
                d_list = _s(gi_overrides.get("D_methods_list_text"))
                d_narr = _s(gi_overrides.get("D_methods_narrative_text"))
                if d_list:
                    for i, it in enumerate([ln.strip() for ln in d_list.splitlines() if ln.strip()], start=1):
                        st.write(f"{i}. {it}")
                st.write(d_narr or "—")

                st.divider()
                _preview_conclusion(conclusion_payload)

    return True
