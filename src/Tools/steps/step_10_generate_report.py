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

# Step 8 outputs
SS_SF_EXTRACTED = "tool6_summary_findings_extracted"  # list[{finding, recommendation}]
SS_SF_SEV_BY_NO = "tool6_severity_by_no"
SS_SF_SEV_BY_FINDING = "tool6_severity_by_finding"
SS_SF_ADD_LEGEND = "tool6_add_legend"

# internal: last generated signature + timestamp
SS_LAST_SIG = "tool6_report_last_sig"
SS_LAST_GEN_TS = "tool6_report_last_generated_ts"

# perf cache for preview rows
SS_S10_PREVIEW_CACHE_SIG = "tool6_s10_preview_cache_sig"
SS_S10_PREVIEW_CACHE_ROWS = "tool6_s10_preview_cache_rows"


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


def _fmt_ts(ts: Any) -> str:
    try:
        ts = float(ts)
    except Exception:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def _inject_css() -> None:
    st.markdown(
        """
<style>
  [data-testid="stVerticalBlock"] { gap: 0.70rem; }

  /* Standard card */
  .t6-card {
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 14px;
    padding: 14px;
    background: rgba(255,255,255,0.02);
    margin: 0.25rem 0 0.75rem 0;
  }
  .t6-card-title {
    font-weight: 700;
    font-size: 0.98rem;
    margin-bottom: 0.35rem;
  }
  .t6-subtle { opacity: 0.85; font-size: 0.92rem; }

  /* Sticky toolbar */
  .t6-sticky {
    position: sticky;
    top: 0;
    z-index: 50;
    background: rgba(255,255,255,0.86);
    backdrop-filter: blur(10px);
    padding: 0.65rem 0.75rem;
    border-radius: 14px;
    border: 1px solid rgba(0,0,0,0.06);
    margin-bottom: 0.75rem;
  }
  @media (prefers-color-scheme: dark) {
    .t6-sticky { background: rgba(10,10,10,0.62); border: 1px solid rgba(255,255,255,0.10); }
    .t6-card { border: 1px solid rgba(255,255,255,0.10); background: rgba(255,255,255,0.03); }
  }

  .t6-pill {
    display: inline-block;
    padding: 0.2rem 0.55rem;
    border-radius: 999px;
    font-weight: 700;
    font-size: 0.85rem;
    border: 1px solid rgba(0,0,0,0.08);
  }
  @media (prefers-color-scheme: dark) {
    .t6-pill { border: 1px solid rgba(255,255,255,0.12); }
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
    obs = st.session_state.get("tool6_component_observations_final")
    if obs is None:
        obs = st.session_state.get("component_observations", [])
    return obs if isinstance(obs, list) else []


# =============================================================================
# Preview helpers (FAST)
# =============================================================================
def _preview_general_info(overrides: Dict[str, Any]) -> None:
    items = [(k, _s(v)) for k, v in (overrides or {}).items() if _s(k)]
    if not items:
        st.info("No General Info overrides found.")
        return

    st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
    st.markdown("<div class='t6-card-title'>General Information (Overrides)</div>", unsafe_allow_html=True)

    left, right = st.columns(2, gap="large")
    half = (len(items) + 1) // 2
    for idx, (k, v) in enumerate(items):
        target = left if idx < half else right
        with target:
            st.markdown(f"**{k}**")
            st.write(v or "—")

    st.markdown("</div>", unsafe_allow_html=True)


def _fallback_extract_summary_findings(component_observations: List[Dict[str, Any]]) -> List[Tuple[str, str, str]]:
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


def _get_summary_findings_preview_rows_fast() -> List[Tuple[str, str, str]]:
    """
    Returns list of (finding, severity, recommendation).
    Caches based on a lightweight signature for speed.
    """
    extracted = st.session_state.get(SS_SF_EXTRACTED) or st.session_state.get("tool6_summary_findings_extracted") or []
    sev_by_no = st.session_state.get(SS_SF_SEV_BY_NO) or {}
    sev_by_finding = st.session_state.get(SS_SF_SEV_BY_FINDING) or {}

    # lightweight sig
    sig = _sha1(
        "|".join(
            [
                f"n={len(extracted) if isinstance(extracted, list) else 0}",
                f"sno={len(sev_by_no) if isinstance(sev_by_no, dict) else 0}",
                f"sf={len(sev_by_finding) if isinstance(sev_by_finding, dict) else 0}",
            ]
        )
    )

    if st.session_state.get(SS_S10_PREVIEW_CACHE_SIG) == sig:
        cached = st.session_state.get(SS_S10_PREVIEW_CACHE_ROWS)
        if isinstance(cached, list):
            return cached

    out: List[Tuple[str, str, str]] = []
    if isinstance(extracted, list) and extracted:
        # fast path: by_no first, then fallback by_finding if needed
        norm_map = {}
        if isinstance(sev_by_finding, dict) and sev_by_finding:
            for k, v in sev_by_finding.items():
                kk = _s(k).strip().lower()
                if kk:
                    norm_map[kk] = _s(v)

        for i, x in enumerate(extracted, start=1):
            if not isinstance(x, dict):
                continue
            f = _s(x.get("finding"))
            r = _s(x.get("recommendation")) or "—"
            if not f:
                continue

            sev = _s(sev_by_no.get(i)) if isinstance(sev_by_no, dict) else ""
            if not sev:
                sev = norm_map.get(f.strip().lower(), "")
            sev = sev or "Medium"
            out.append((f, sev, r))

        st.session_state[SS_S10_PREVIEW_CACHE_SIG] = sig
        st.session_state[SS_S10_PREVIEW_CACHE_ROWS] = out
        return out

    # fallback
    out = _fallback_extract_summary_findings(_get_component_observations())
    st.session_state[SS_S10_PREVIEW_CACHE_SIG] = sig
    st.session_state[SS_S10_PREVIEW_CACHE_ROWS] = out
    return out


def _preview_findings_table_fast(max_rows: int = 80) -> None:
    rows = _get_summary_findings_preview_rows_fast()
    if not rows:
        st.info("No findings captured yet to preview.")
        return

    st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
    st.markdown("<div class='t6-card-title'>Summary of Findings (Preview)</div>", unsafe_allow_html=True)
    st.markdown("<div class='t6-subtle'>Preview is capped for speed. Final DOCX uses full data.</div>", unsafe_allow_html=True)

    # Use st.dataframe for speed (markdown tables are slower on large content)
    show = rows[: max(1, int(max_rows))]
    df = {
        "No.": list(range(1, len(show) + 1)),
        "Finding": [f for f, _, _ in show],
        "Severity": [sev for _, sev, _ in show],
        "Recommendation / Corrective Action": [r for _, _, r in show],
    }
    st.dataframe(df, use_container_width=True, hide_index=True)

    if len(rows) > len(show):
        st.info(f"Showing {len(show)} of {len(rows)} rows for preview speed.")

    st.markdown("</div>", unsafe_allow_html=True)


def _preview_conclusion(conclusion_payload: Dict[str, Any]) -> None:
    txt = _s(conclusion_payload.get("conclusion_text"))
    kp = conclusion_payload.get("key_points") or []
    reco = _s(conclusion_payload.get("recommendations_summary"))

    st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
    st.markdown("<div class='t6-card-title'>Conclusion</div>", unsafe_allow_html=True)

    st.write(txt or "—")

    if isinstance(kp, list) and any(_s(x) for x in kp):
        st.markdown("**Key Points**")
        for it in kp:
            if _s(it):
                st.write(f"• {_s(it)}")

    if reco:
        st.markdown("**Recommendations Summary**")
        st.write(reco)

    st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# Readiness + signature (LIGHT)
# =============================================================================
def _readiness_flags(*, cover_bytes: Optional[bytes]) -> Dict[str, bool]:
    gi = st.session_state.get(SS_GI, {}) or {}
    component_observations = _get_component_observations()
    conclusion_payload = st.session_state.get(SS_CONCLUSION_PAYLOAD, {}) or {}

    gi_ok = bool(gi)
    obs_ok = bool(component_observations)

    exec_ok = bool(_s(gi.get("Executive Summary Text")))
    dcm_ok = bool(_s(gi.get("D_methods_list_text"))) and bool(_s(gi.get("D_methods_narrative_text")))
    conclusion_ok = bool(_s(conclusion_payload.get("conclusion_text"))) or bool(conclusion_payload)

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

    n_find = len(st.session_state.get(SS_SF_EXTRACTED) or st.session_state.get("tool6_summary_findings_extracted") or [])

    sig = _sha1(
        "|".join(
            [
                str(bool(cover_bytes)),
                str(len(gi)),
                _s(gi.get("Executive Summary Text"))[:80],
                _s(gi.get("D_methods_list_text"))[:80],
                _s(gi.get("D_methods_narrative_text"))[:80],
                _s(conclusion_payload.get("conclusion_text"))[:80],
                f"n_find={n_find}",
            ]
        )
    )
    return sig


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
    Step 10 — Generate Report (Standard, aligned, FAST)
    - Sticky dashboard
    - Preview OFF by default
    - Preview is capped for speed
    - Signature detects stale DOCX
    """
    _inject_css()

    gi_overrides: Dict[str, Any] = st.session_state.get(SS_GI, {}) or {}
    conclusion_payload = st.session_state.get(SS_CONCLUSION_PAYLOAD, {}) or {}

    # cover bytes (must be fast)
    try:
        cover_bytes = resolve_cover_bytes()
    except Exception as e:
        cover_bytes = None
        st.error(f"Cover resolver failed: {e}")

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
    st.markdown('<div class="t6-sticky">', unsafe_allow_html=True)
    a1, a2, a3, a4 = st.columns([1.40, 1.15, 1.10, 1.35], gap="small")

    with a1:
        st.markdown("**Readiness**")
        st.progress(ok_count / max(1, total))
        st.markdown(f"<div class='t6-subtle'>{ok_count}/{total} sections ready</div>", unsafe_allow_html=True)

    with a2:
        st.markdown("**Build signature**")
        st.code(sig, language="text")

    with a3:
        st.markdown("**Last generated**")
        st.markdown(f"<div class='t6-subtle'>{_fmt_ts(last_ts)}</div>", unsafe_allow_html=True)
        if stale:
            st.warning("DOCX is outdated (inputs changed).")

    with a4:
        show_preview = st.toggle(
            "Show Preview",
            value=False,
            key=_key("show_preview"),
            help="Preview is off by default for speed.",
        )

    st.markdown("</div>", unsafe_allow_html=True)

    # ---------------- Main card ----------------
    with st.container(border=True):
        card_open(
            "Generate & Download",
            subtitle="Confirm readiness and generate the DOCX. Preview is optional.",
            variant="lg-variant-cyan",
        )

        # readiness grid (aligned)
        st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
        st.markdown("<div class='t6-card-title'>Readiness checklist</div>", unsafe_allow_html=True)

        cols = st.columns(3, gap="small")
        items = list(flags.items())
        for i, (name, ok) in enumerate(items):
            with cols[i % 3]:
                st.write(("✅ " if ok else "⚠️ ") + name)

        st.markdown("</div>", unsafe_allow_html=True)

        # guardrails
        if not cover_bytes:
            status_card("Missing cover", "Cover photo is required. Complete Step 1 first.", level="error")
        elif ok_count < total:
            status_card(
                "Not fully ready",
                "Some sections are missing/incomplete. You can still generate, but output may be incomplete.",
                level="warning",
            )
        else:
            status_card("Ready", "All required sections appear to be available.", level="success")

        st.divider()

        # generate flow (aligned)
        st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
        st.markdown("<div class='t6-card-title'>Generate</div>", unsafe_allow_html=True)

        g1, g2, g3 = st.columns([1.35, 1.05, 1.60], gap="small")
        with g1:
            confirm = st.checkbox(
                "I confirm the inputs are ready for final generation.",
                value=False,
                key=_key("confirm"),
                help="Prevents accidental generation.",
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
                st.success("A fresh DOCX is available.")
            elif has_docx and stale:
                st.warning("A DOCX exists, but it’s stale. Re-generate for latest.")
            else:
                st.caption("No DOCX generated yet.")

        st.markdown("</div>", unsafe_allow_html=True)

        # generate action (NO heavy preview work here)
        if clicked:
            with st.spinner("Generating DOCX..."):
                ok = bool(on_generate_docx())
            if ok:
                st.session_state[SS_LAST_SIG] = sig
                st.session_state[SS_LAST_GEN_TS] = time.time()
                status_card("Generated", "DOCX generated successfully. Download below.", level="success")
            else:
                status_card("Failed", "DOCX generation failed. Check inputs and try again.", level="error")

        # download
        docx_bytes = st.session_state.get(SS_DOCX_BYTES)
        if docx_bytes:
            st.download_button(
                "⬇️ Download Word (DOCX)",
                data=docx_bytes,
                file_name=f"Tool6_Report_{_s(getattr(ctx, 'tpm_id', '')) or 'TPM'}.docx",
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
                st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
                st.markdown("<div class='t6-card-title'>Cover</div>", unsafe_allow_html=True)
                if cover_bytes:
                    st.image(cover_bytes, caption="Cover photo", use_container_width=True)
                else:
                    st.warning("Cover photo is missing.")
                st.markdown("</div>", unsafe_allow_html=True)

            elif pick == "General Information":
                _preview_general_info(gi_overrides)

            elif pick == "Summary of Findings":
                _preview_findings_table_fast(max_rows=80)

            elif pick == "Executive Summary":
                st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
                st.markdown("<div class='t6-card-title'>Executive Summary</div>", unsafe_allow_html=True)
                exec_txt = _s(gi_overrides.get("Executive Summary Text"))
                st.write(exec_txt or "—")
                st.markdown("</div>", unsafe_allow_html=True)

            elif pick == "Data Collection Methods":
                st.markdown("<div class='t6-card'>", unsafe_allow_html=True)
                st.markdown("<div class='t6-card-title'>Data Collection Methods</div>", unsafe_allow_html=True)
                d_list = _s(gi_overrides.get("D_methods_list_text"))
                d_narr = _s(gi_overrides.get("D_methods_narrative_text"))
                if d_list:
                    items = [ln.strip() for ln in d_list.splitlines() if ln.strip()]
                    for i, it in enumerate(items, start=1):
                        st.write(f"{i}. {it}")
                st.write(d_narr or "—")
                if (not d_list) and (not d_narr):
                    st.info("Not found. Step 7 should save it into overrides.")
                st.markdown("</div>", unsafe_allow_html=True)

            elif pick == "Conclusion":
                _preview_conclusion(conclusion_payload)

        with tab2:
            with st.expander("Show full preview (capped for speed)", expanded=False):
                # still avoid huge renders
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
                _preview_findings_table_fast(max_rows=80)

                st.divider()
                st.markdown("## Executive Summary")
                st.write(_s(gi_overrides.get("Executive Summary Text")) or "—")

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
