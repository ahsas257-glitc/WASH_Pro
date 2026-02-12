from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import hashlib
import time

import streamlit as st

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import status_card


# =============================================================================
# Session keys
# =============================================================================
SS_GI = "general_info_overrides"
SS_DOCX_BYTES = "tool6_docx_bytes"
SS_CONCLUSION_PAYLOAD = "tool6_conclusion_payload"

SS_SF_EXTRACTED = "tool6_summary_findings_extracted"
SS_SF_SEV_BY_NO = "tool6_severity_by_no"
SS_SF_SEV_BY_FINDING = "tool6_severity_by_finding"

SS_LAST_SIG = "tool6_report_last_sig"
SS_LAST_GEN_TS = "tool6_report_last_generated_ts"

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
    return "t6.s10." + hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()


def _fmt_ts(ts: Any) -> str:
    try:
        ts = float(ts)
    except Exception:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


# =============================================================================
# Minimal + precise CSS (NO extra cards / containers)
# =============================================================================
def _inject_css() -> None:
    st.markdown(
        """
<style>
.t6-s10-wrap {
  max-width: 1180px;
  margin-left: auto;
  margin-right: auto;
}

div[data-testid="stHorizontalBlock"] { align-items: stretch; }
div[data-testid="column"] {
  display: flex;
  flex-direction: column;
  align-self: stretch;
}

[data-testid="stVerticalBlock"] { gap: 0.75rem; }

.t6-s10-sticky {
  position: sticky;
  top: 0.25rem;
  z-index: 90;
  backdrop-filter: blur(10px);
  padding: 0.75rem 0.9rem;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.10);
  background: rgba(15,15,18,0.55);
  margin-bottom: 1rem;
}

.t6-s10-section {
  padding: 0.75rem 0;
}

.t6-s10-title {
  font-weight: 700;
  margin-bottom: 0.35rem;
}

.t6-s10-subtle {
  opacity: 0.85;
  font-size: 0.92rem;
}

.t6-s10-pill {
  display: inline-block;
  padding: 0.25rem 0.65rem;
  border-radius: 999px;
  font-weight: 700;
  font-size: 0.85rem;
  border: 1px solid rgba(255,255,255,0.12);
}

@media (max-width: 900px) {
  div[data-testid="column"] {
    width: 100% !important;
    flex: 1 1 100% !important;
  }
  .t6-s10-sticky {
    position: relative !important;
    top: unset !important;
  }
}
</style>
""",
        unsafe_allow_html=True,
    )


# =============================================================================
# Data helpers (FAST + bounded)
# =============================================================================
def _get_component_observations() -> List[Dict[str, Any]]:
    obs = st.session_state.get("tool6_component_observations_final")
    if obs is None:
        obs = st.session_state.get("component_observations", [])
    return obs if isinstance(obs, list) else []


def _get_summary_findings_preview_rows_fast() -> List[Tuple[str, str, str]]:
    extracted = (
        st.session_state.get(SS_SF_EXTRACTED)
        or st.session_state.get("tool6_summary_findings_extracted")
        or []
    )
    sev_by_no = st.session_state.get(SS_SF_SEV_BY_NO) or {}
    sev_by_finding = st.session_state.get(SS_SF_SEV_BY_FINDING) or {}

    sig = _sha1(
        f"n={len(extracted)}|s1={len(sev_by_no)}|s2={len(sev_by_finding)}"
    )

    if st.session_state.get(SS_S10_PREVIEW_CACHE_SIG) == sig:
        cached = st.session_state.get(SS_S10_PREVIEW_CACHE_ROWS)
        if isinstance(cached, list):
            return cached

    rows: List[Tuple[str, str, str]] = []

    norm_map = {
        _s(k).strip().lower(): _s(v)
        for k, v in (sev_by_finding or {}).items()
    }

    for i, item in enumerate(extracted or [], start=1):
        if not isinstance(item, dict):
            continue
        f = _s(item.get("finding"))
        r = _s(item.get("recommendation")) or "—"
        if not f:
            continue
        sev = _s(sev_by_no.get(i)) or norm_map.get(f.lower()) or "Medium"
        rows.append((f, sev, r))

    st.session_state[SS_S10_PREVIEW_CACHE_SIG] = sig
    st.session_state[SS_S10_PREVIEW_CACHE_ROWS] = rows
    return rows


# =============================================================================
# Readiness
# =============================================================================
def _readiness_flags(cover_bytes: Optional[bytes]) -> Dict[str, bool]:
    gi = st.session_state.get(SS_GI, {}) or {}
    conclusion = st.session_state.get(SS_CONCLUSION_PAYLOAD, {}) or {}
    findings = (
        st.session_state.get(SS_SF_EXTRACTED)
        or st.session_state.get("tool6_summary_findings_extracted")
        or []
    )

    return {
        "Cover": bool(cover_bytes),
        "General Info": bool(gi),
        "Findings": bool(findings),
        "Executive Summary": bool(_s(gi.get("Executive Summary Text"))),
        "Data Collection": bool(_s(gi.get("D_methods_list_text"))),
        "Conclusion": bool(_s(conclusion.get("conclusion_text"))),
    }


def _build_signature(cover_bytes: Optional[bytes]) -> str:
    gi = st.session_state.get(SS_GI, {}) or {}
    conclusion = st.session_state.get(SS_CONCLUSION_PAYLOAD, {}) or {}
    n_find = len(
        st.session_state.get(SS_SF_EXTRACTED)
        or st.session_state.get("tool6_summary_findings_extracted")
        or []
    )

    return _sha1(
        "|".join(
            [
                str(bool(cover_bytes)),
                str(len(gi)),
                _s(gi.get("Executive Summary Text"))[:60],
                _s(conclusion.get("conclusion_text"))[:60],
                f"n={n_find}",
            ]
        )
    )


# =============================================================================
# MAIN
# =============================================================================
def render_step(
    ctx: Tool6Context,
    *,
    resolve_cover_bytes,
    on_generate_docx,
) -> bool:

    _inject_css()

    try:
        cover_bytes = resolve_cover_bytes()
    except Exception:
        cover_bytes = None

    flags = _readiness_flags(cover_bytes)
    ok_count = sum(1 for v in flags.values() if v)
    total = len(flags)

    sig = _build_signature(cover_bytes)
    last_sig = _s(st.session_state.get(SS_LAST_SIG))
    last_ts = st.session_state.get(SS_LAST_GEN_TS)
    docx_bytes = st.session_state.get(SS_DOCX_BYTES)

    stale = bool(docx_bytes and last_sig and last_sig != sig)

    st.markdown("<div class='t6-s10-wrap'>", unsafe_allow_html=True)

    # ================= Sticky Header =================
    st.markdown("<div class='t6-s10-sticky'>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([1.3, 1.2, 1.1, 1.4], gap="small")

    with c1:
        st.markdown("**Readiness**")
        st.progress(ok_count / max(1, total))
        st.markdown(
            f"<div class='t6-s10-subtle'>{ok_count}/{total} ready</div>",
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown("**Build signature**")
        st.code(sig, language="text")

    with c3:
        st.markdown("**Last generated**")
        st.markdown(
            f"<div class='t6-s10-subtle'>{_fmt_ts(last_ts)}</div>",
            unsafe_allow_html=True,
        )
        if stale:
            st.warning("DOCX is outdated.")

    with c4:
        show_preview = st.toggle(
            "Show Preview",
            key=_key("preview"),
            value=False,
        )

    st.markdown("</div>", unsafe_allow_html=True)

    # ================= Readiness grid =================
    st.markdown("<div class='t6-s10-section'>", unsafe_allow_html=True)
    cols = st.columns(3, gap="small")
    for i, (name, ok) in enumerate(flags.items()):
        with cols[i % 3]:
            st.write(("✅ " if ok else "⚠️ ") + name)
    st.markdown("</div>", unsafe_allow_html=True)

    # ================= Generate =================
    g1, g2, g3 = st.columns([1.4, 1.1, 1.5], gap="small")

    with g1:
        confirm = st.checkbox(
            "I confirm inputs are final.",
            key=_key("confirm"),
        )

    with g2:
        clicked = st.button(
            "🚀 Generate DOCX",
            use_container_width=True,
            disabled=(not confirm) or (not cover_bytes),
            type="primary",
            key=_key("generate"),
        )

    with g3:
        if docx_bytes and not stale:
            st.success("Fresh DOCX available.")
        elif docx_bytes and stale:
            st.warning("Existing DOCX is stale.")
        else:
            st.caption("No DOCX generated yet.")

    if clicked:
        with st.spinner("Generating..."):
            ok = bool(on_generate_docx())
        if ok:
            st.session_state[SS_LAST_SIG] = sig
            st.session_state[SS_LAST_GEN_TS] = time.time()
            status_card("Generated", "DOCX created successfully.", level="success")
        else:
            status_card("Failed", "Generation failed.", level="error")

    if st.session_state.get(SS_DOCX_BYTES):
        st.download_button(
            "⬇️ Download DOCX",
            data=st.session_state[SS_DOCX_BYTES],
            file_name=f"Tool6_Report_{_s(getattr(ctx, 'tpm_id', 'TPM'))}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
            key=_key("download"),
        )

    # ================= Preview (ON DEMAND) =================
    if show_preview:
        st.divider()
        section = st.selectbox(
            "Preview section",
            [
                "Cover",
                "General Info",
                "Findings",
                "Executive Summary",
                "Conclusion",
            ],
            label_visibility="collapsed",
            key=_key("section_pick"),
        )

        if section == "Cover":
            if cover_bytes:
                st.image(cover_bytes, use_container_width=True)
            else:
                st.warning("No cover image.")

        elif section == "General Info":
            gi = st.session_state.get(SS_GI, {}) or {}
            for k, v in gi.items():
                if _s(k):
                    st.markdown(f"**{k}**")
                    st.write(_s(v) or "—")

        elif section == "Findings":
            rows = _get_summary_findings_preview_rows_fast()[:80]
            if rows:
                df = {
                    "No.": list(range(1, len(rows) + 1)),
                    "Finding": [f for f, _, _ in rows],
                    "Severity": [s for _, s, _ in rows],
                    "Recommendation": [r for _, _, r in rows],
                }
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No findings available.")

        elif section == "Executive Summary":
            gi = st.session_state.get(SS_GI, {}) or {}
            st.write(_s(gi.get("Executive Summary Text")) or "—")

        elif section == "Conclusion":
            conclusion = st.session_state.get(SS_CONCLUSION_PAYLOAD, {}) or {}
            st.write(_s(conclusion.get("conclusion_text")) or "—")

    st.markdown("</div>", unsafe_allow_html=True)

    return True
