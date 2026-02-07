from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

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
SS_ROWS = "tool6_summary_findings_rows"                 # list[dict]
SS_LOCK = "tool6_summary_findings_lock"                 # bool: user confirmed
SS_SOURCE_FP = "tool6_summary_findings_fp"              # str: signature of section5 data

# Outputs used by builder / step10
SS_SEVERITY_BY_NO = "tool6_severity_by_no"              # Dict[int, str]
SS_SEVERITY_BY_FINDING = "tool6_severity_by_finding"    # Dict[str, str]
SS_ADD_LEGEND = "tool6_add_legend"                      # bool

# Extracted rows used by report section 6
SS_EXTRACTED = "tool6_summary_findings_extracted"       # list[{finding, recommendation}]

# UX / autosave perf
SS_EDITOR_DATA = "tool6_s8_editor_data"                 # st.data_editor return store
SS_DATA_HASH = "tool6_s8_data_hash"                     # last saved hash
SS_LAST_SAVE_TS = "tool6_s8_last_save_ts"               # str timestamp
SS_DIRTY = "tool6_s8_dirty"                             # bool


# =============================================================================
# Small helpers (fast + safe)
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"t6.s8.{h}"


def _now_hhmmss() -> str:
    return datetime.now().strftime("%H:%M:%S")


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


def _clamp_words(text: str, max_words: int) -> str:
    parts = [p for p in re.split(r"\s+", _s(text)) if p]
    if not parts:
        return ""
    if len(parts) <= max_words:
        return " ".join(parts)
    return " ".join(parts[:max_words]).strip()


def _clean_for_title(text: str) -> str:
    t = _s(text)
    t = re.sub(r"[\r\n\t]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^[•\-\–\—\*]+\s*", "", t).strip()
    t = t.strip(" .;:,-")
    return t


def _df_hash(df: "pd.DataFrame") -> str:
    """
    Hash only the relevant text columns to detect changes quickly.
    """
    try:
        cols = ["Finding", "Severity", "Recommendation / Corrective Action"]
        blob = []
        for _, r in df[cols].fillna("").iterrows():
            blob.append("|".join([_s(r.get(c)) for c in cols]))
        raw = "\n".join(blob).encode("utf-8", errors="ignore")
        return hashlib.sha1(raw).hexdigest()[:16]
    except Exception:
        return "unknown"


# =============================================================================
# 1) Finding title builder (short + logical)
# =============================================================================
STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "by", "for", "with",
    "is", "are", "was", "were", "be", "been", "being", "this", "that", "these", "those",
    "there", "here", "it", "its", "as", "from", "into", "over", "under",
    "observed", "observation", "finding", "issue", "problem", "noted",
}


def _make_finding_title(component: str, finding_raw: str) -> str:
    """
    Build a short, meaningful title for the Finding column.
    Output example: "Pump — Leakage at flange joint."
    """
    comp = _clean_for_title(component)
    f = _clean_for_title(finding_raw)

    if not f and comp:
        return f"{comp} — General issue."
    if not f:
        return "General issue."

    f = re.split(r"[.!?]\s+", f, maxsplit=1)[0].strip()
    f = re.sub(r"\([^)]*\)", "", f).strip()

    tokens = [t for t in re.split(r"[^\w]+", f) if t]
    kept: List[str] = []
    for t in tokens:
        tl = t.lower()
        if tl in STOPWORDS:
            continue
        if len(t) <= 1:
            continue
        kept.append(t)

    core = " ".join(kept) if kept else f
    core = _clamp_words(core, 10)
    core = core.strip(" .;:,-")

    if core and core[0].isalpha():
        core = core[0].upper() + core[1:]

    title = f"{comp} — {core}" if comp else core
    title = title.strip()
    if title and title[-1] not in ".!?":
        title += "."
    return title


# =============================================================================
# 2) Severity inference (rule-based scoring)
# =============================================================================
HIGH_PATTERNS = [
    r"\bnot\s+functional\b", r"\bnon[-\s]?functional\b",
    r"\bunsafe\b", r"\bhazard\b", r"\belectric(al)?\s+hazard\b",
    r"\bcontaminat(ed|ion)\b", r"\bopen\s+sewage\b", r"\bsewage\b",
    r"\bstructural\b.*\bfail(ure|ed)\b", r"\bcollapse\b",
    r"\bleak(age|ing)\b.*\bmajor\b", r"\bno\s+disinfect(ion|ant)\b",
    r"\bno\s+chlorin(e|ation)\b", r"\bcritical\b", r"\bimmediate\b",
    r"\bserious\b", r"\bhigh\s+risk\b", r"\bchild\b.*\brisk\b",
    r"\bwater\s+quality\b.*\bfail\b", r"\bE\.?\s*coli\b",
    r"\bcompliance\b.*\bfail\b", r"\bviolat(ion|e)\b",
]

MED_PATTERNS = [
    r"\bpartially\b", r"\bpartial\b",
    r"\bneeds?\s+repair\b", r"\bmaintenance\b", r"\bservice\b",
    r"\bdamaged\b", r"\bcrack(s)?\b", r"\bleak(age|ing)\b",
    r"\bpoor\b", r"\binadequate\b", r"\binsufficient\b",
    r"\bmissing\b", r"\bmalfunction\b", r"\bblocked\b",
    r"\blow\s+performance\b", r"\bmoderate\b",
    r"\bnon[-\s]?compliance\b", r"\bimprovement\b\s+needed\b",
]

LOW_PATTERNS = [
    r"\bminor\b", r"\bcosmetic\b",
    r"\bsmall\b", r"\blabel\b", r"\bsignage\b",
    r"\bclean(liness)?\b", r"\btidy\b", r"\bpaint\b",
    r"\brecommended\b", r"\bshould\b",
]


def _score_patterns(text: str, patterns: List[str]) -> int:
    t = _s(text).lower()
    if not t:
        return 0
    score = 0
    for p in patterns:
        if re.search(p, t, flags=re.IGNORECASE):
            score += 1
    return score


def _infer_severity(finding_raw: str, reco_raw: str) -> str:
    """
    Returns: High / Medium / Low based on simple, explainable rules.
    """
    text = f"{_s(finding_raw)} | {_s(reco_raw)}"
    lo_text = text.lower()

    hi = _score_patterns(text, HIGH_PATTERNS)
    med = _score_patterns(text, MED_PATTERNS)
    lo = _score_patterns(text, LOW_PATTERNS)

    if hi >= 1 and ("immediate" in lo_text or "unsafe" in lo_text or "not functional" in lo_text):
        return "High"
    if hi >= 2 and hi >= med:
        return "High"
    if med >= 1:
        return "Medium"
    if lo >= 1:
        return "Low"
    return "Medium"


# =============================================================================
# 3) Recommendation summarizer (short + logical)
# =============================================================================
def _summarize_reco(recos: List[str], fallback: str = "") -> str:
    items = [_clean_for_title(x) for x in (recos or []) if _clean_for_title(x)]
    if not items and _clean_for_title(fallback):
        items = [_clean_for_title(fallback)]
    if not items:
        return "—"

    seen = set()
    uniq: List[str] = []
    for it in items:
        key = it.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    top = uniq[:2]
    top = [_clamp_words(x, 18).strip(" .;:,-") for x in top if x]

    out = " ".join([_norm_sentence(x) for x in top if x]).strip()
    if not out:
        return "—"
    if len(out) > 240:
        out = out[:237].rstrip() + "..."
    return out


# =============================================================================
# Section 5 fingerprint & extraction
# =============================================================================
def _fp_section5(component_observations: Any) -> str:
    """
    Fast fingerprint: titles + findings + recommendations count.
    """
    if not isinstance(component_observations, list) or not component_observations:
        return "empty"

    pieces: List[str] = []
    try:
        for comp in component_observations[:12]:
            if not isinstance(comp, dict):
                continue
            pieces.append(_s(comp.get("component") or comp.get("title") or comp.get("name")))
            ov = comp.get("observations_valid") or []
            if not isinstance(ov, list):
                continue
            for ob in ov[:20]:
                if not isinstance(ob, dict):
                    continue
                pieces.append(_s(ob.get("title")))
                mt = ob.get("major_table") or []
                if isinstance(mt, list):
                    for r in mt[:10]:
                        if isinstance(r, dict):
                            pieces.append(_s(r.get("finding")))
                recs = ob.get("recommendations") or []
                if isinstance(recs, list):
                    pieces.append(f"recs={len([x for x in recs if _s(x)])}")

        raw = "|".join(pieces)
        return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    except Exception:
        return "unknown"


def _extract_from_section5(component_observations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    for comp in component_observations or []:
        if not isinstance(comp, dict):
            continue

        comp_name = _s(comp.get("component") or comp.get("title") or comp.get("name") or "Component")

        ov = comp.get("observations_valid") or []
        if not isinstance(ov, list):
            continue

        for ob in ov:
            if not isinstance(ob, dict):
                continue

            mt = ob.get("major_table") or []
            recs = ob.get("recommendations") or []

            if isinstance(mt, list) and mt:
                for r in mt:
                    if not isinstance(r, dict):
                        continue
                    f = _s(r.get("finding"))
                    if not f:
                        continue
                    out.append(
                        {
                            "component": comp_name,
                            "finding_raw": f,
                            "recs": recs if isinstance(recs, list) else [],
                            "recommendation_raw": _s(r.get("recommendation")) or _s(r.get("corrective_action")) or "",
                        }
                    )
            else:
                if isinstance(recs, list) and any(_s(x) for x in recs):
                    out.append(
                        {
                            "component": comp_name,
                            "finding_raw": _s(ob.get("title")) or "Finding",
                            "recs": recs,
                            "recommendation_raw": "",
                        }
                    )

    return out


def _default_rows(component_observations: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    extracted = _extract_from_section5(component_observations or [])
    rows: List[Dict[str, str]] = []

    for it in extracted:
        comp = _s(it.get("component"))
        f_raw = _s(it.get("finding_raw"))
        recs = it.get("recs") if isinstance(it.get("recs"), list) else []
        reco_raw = _s(it.get("recommendation_raw"))

        finding_title = _make_finding_title(comp, f_raw)
        reco_short = _summarize_reco([_s(x) for x in recs if _s(x)], fallback=reco_raw)
        sev = _infer_severity(f_raw, reco_short)

        rows.append(
            {
                "No.": "",
                "Finding": finding_title,
                "Severity": sev,
                "Recommendation / Corrective Action": reco_short,
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
    extracted: List[Dict[str, str]] = []
    severity_by_no: Dict[int, str] = {}
    severity_by_finding: Dict[str, str] = {}

    n = 0
    for r in rows or []:
        finding = _norm_sentence(r.get("Finding"))
        reco = _norm_sentence(r.get("Recommendation / Corrective Action")) or "—"
        sev = _s(r.get("Severity")) or "Medium"

        if not _s(finding).strip(". "):
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
    ss.setdefault(SS_EXTRACTED, [])

    ss.setdefault(SS_DATA_HASH, "")
    ss.setdefault(SS_LAST_SAVE_TS, "")
    ss.setdefault(SS_DIRTY, False)

    fp = _fp_section5(component_observations)

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


def _inject_table_css() -> None:
    st.markdown(
        """
<style>
.t6-s8-sticky {
  position: sticky;
  top: 0;
  z-index: 50;
  background: rgba(255,255,255,0.78);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(0,0,0,0.06);
  border-radius: 14px;
  padding: 0.6rem 0.75rem;
  margin-bottom: 0.75rem;
}

@media (prefers-color-scheme: dark) {
  .t6-s8-sticky {
    background: rgba(10,10,10,0.55);
    border: 1px solid rgba(255,255,255,0.10);
  }
}

.t6-s8-subtle {
  opacity: 0.85;
  font-size: 0.92rem;
}

.t6-s8-pill {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 999px;
  font-weight: 700;
  font-size: 0.85rem;
  border: 1px solid rgba(0,0,0,0.08);
}

@media (prefers-color-scheme: dark) {
  .t6-s8-pill { border: 1px solid rgba(255,255,255,0.12); }
}
</style>
""",
        unsafe_allow_html=True,
    )


# =============================================================================
# Main renderer
# =============================================================================
def render_step(ctx: Tool6Context, *, title: str = "Step 8 — Summary of Findings") -> bool:
    if pd is None:
        st.error("pandas is required for Step 8. Please install pandas.")
        return False

    _ = ctx
    _inject_table_css()

    st.subheader(title)
    st.caption("Auto-generated from Section 5. You can edit findings, severity, and recommendations. Changes auto-save instantly.")

    component_observations = st.session_state.get("tool6_component_observations_final")
    if component_observations is None:
        component_observations = st.session_state.get("component_observations", [])

    if not isinstance(component_observations, list):
        component_observations = []

    _ensure_state(component_observations)

    with st.container(border=True):
        card_open(
            "Summary of the findings",
            subtitle="Auto-generated from Step 3/4 (Section 5). Edit severity and recommendations here. Auto-save is enabled.",
            variant="lg-variant-cyan",
        )

        # ---------------------------------------------------------
        # Sticky toolbar (less scrolling + modern UX)
        # ---------------------------------------------------------
        st.markdown('<div class="t6-s8-sticky">', unsafe_allow_html=True)
        t1, t2, t3, t4, t5 = st.columns([1.1, 1.4, 1.2, 1.2, 2.1], gap="small")

        with t1:
            st.session_state[SS_LOCK] = st.toggle(
                "Confirmed",
                value=bool(st.session_state.get(SS_LOCK, False)),
                key=_key("confirm_lock"),
                help="If ON, this step will not auto-refresh when Section 5 changes.",
            )

        with t2:
            if st.button("Auto-generate from Section 5", use_container_width=True, key=_key("reset")):
                st.session_state[SS_ROWS] = _default_rows(component_observations)
                st.session_state[SS_SOURCE_FP] = _fp_section5(component_observations)
                st.session_state[SS_LOCK] = False
                st.session_state[SS_DATA_HASH] = ""
                st.session_state[SS_DIRTY] = False
                st.rerun()

        with t3:
            st.session_state[SS_ADD_LEGEND] = st.toggle(
                "Add legend",
                value=bool(st.session_state.get(SS_ADD_LEGEND, True)),
                key=_key("legend"),
                help="Adds severity legend in the report.",
            )

        with t4:
            if st.button("Clean empty rows", use_container_width=True, key=_key("clean_empty")):
                cur = st.session_state.get(SS_ROWS) or []
                cleaned = []
                for r in cur:
                    if not isinstance(r, dict):
                        continue
                    if _s(r.get("Finding")) or _s(r.get("Recommendation / Corrective Action")):
                        cleaned.append(r)
                st.session_state[SS_ROWS] = cleaned or _default_rows(component_observations)
                st.session_state[SS_DATA_HASH] = ""
                st.session_state[SS_DIRTY] = False
                st.rerun()

        with t5:
            # Save status
            dirty = bool(st.session_state.get(SS_DIRTY, False))
            last_ts = _s(st.session_state.get(SS_LAST_SAVE_TS))
            if dirty:
                st.markdown("<span class='t6-s8-pill'>⚠️ Unsaved changes</span>", unsafe_allow_html=True)
            else:
                msg = f"✅ Saved{(' at ' + last_ts) if last_ts else ''}"
                st.markdown(f"<span class='t6-s8-pill'>{msg}</span>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # ---------------------------------------------------------
        # Tabs: Table / Preview / Export (modern + low clutter)
        # ---------------------------------------------------------
        tab_table, tab_preview, tab_export = st.tabs(["Table", "Preview", "Export"])

        # Prepare DataFrame
        rows = st.session_state.get(SS_ROWS) or []
        for i, r in enumerate(rows, start=1):
            if isinstance(r, dict):
                r["No."] = str(i)

        df = pd.DataFrame(rows, columns=["No.", "Finding", "Severity", "Recommendation / Corrective Action"])

        # ------------------ TABLE TAB ------------------
        with tab_table:
            st.markdown("**Edit the table below** (auto-save is ON).")

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

            # Quick tools row
            q1, q2, q3 = st.columns([1.2, 1.2, 1.6], gap="small")
            with q1:
                if st.button("Auto-infer missing severity", use_container_width=True, key=_key("infer_missing")):
                    tmp = edited_df.copy()
                    for idx, r in tmp.iterrows():
                        sev = _s(r.get("Severity"))
                        finding = _s(r.get("Finding"))
                        reco = _s(r.get("Recommendation / Corrective Action"))
                        if finding and (sev not in ("High", "Medium", "Low")):
                            tmp.at[idx, "Severity"] = _infer_severity(finding, reco)
                    edited_df = tmp
                    st.session_state[SS_DATA_HASH] = ""
                    st.session_state[SS_DIRTY] = True
                    st.rerun()

            with q2:
                if st.button("Normalize texts", use_container_width=True, key=_key("normalize")):
                    tmp = edited_df.copy()
                    for idx, r in tmp.iterrows():
                        tmp.at[idx, "Finding"] = _norm_sentence(r.get("Finding"))
                        reco = _s(r.get("Recommendation / Corrective Action"))
                        tmp.at[idx, "Recommendation / Corrective Action"] = _norm_sentence(reco) or ("—" if reco.strip() == "" else reco)
                    edited_df = tmp
                    st.session_state[SS_DATA_HASH] = ""
                    st.session_state[SS_DIRTY] = True
                    st.rerun()

            with q3:
                st.caption("Tip: Add rows using the + button in the table. Remove empty rows using toolbar.")

        # ------------------ PREVIEW TAB ------------------
        with tab_preview:
            st.markdown("**Report-like preview** (what will be printed).")
            with st.container(border=True):
                items = []
                for _, r in edited_df.fillna("").iterrows():
                    f = _norm_sentence(r.get("Finding"))
                    sev = _s(r.get("Severity")) or "Medium"
                    reco = _norm_sentence(r.get("Recommendation / Corrective Action")) or "—"
                    if _s(f).strip(". "):
                        items.append((sev, f, reco))

                if not items:
                    st.info("No valid findings yet.")
                else:
                    for i, (sev, f, reco) in enumerate(items, start=1):
                        st.markdown(f"**{i}. [{sev}]** {f}")
                        st.markdown(f"- Recommendation: {reco}")

        # ------------------ EXPORT TAB ------------------
        with tab_export:
            st.markdown("**Export table (CSV)**")
            csv_bytes = edited_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download CSV",
                data=csv_bytes,
                file_name="summary_of_findings.csv",
                mime="text/csv",
                use_container_width=True,
                key=_key("dl_csv"),
            )

        # ---------------------------------------------------------
        # AUTO-SAVE (fast + only when changed)
        # ---------------------------------------------------------
        current_hash = _df_hash(edited_df)
        last_hash = _s(st.session_state.get(SS_DATA_HASH))

        if current_hash != last_hash:
            # Convert df -> rows
            new_rows: List[Dict[str, str]] = []
            for _, r in edited_df.fillna("").iterrows():
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

            st.session_state[SS_SEVERITY_BY_NO] = sev_by_no
            st.session_state[SS_SEVERITY_BY_FINDING] = sev_by_finding
            st.session_state[SS_EXTRACTED] = extracted

            # Compatibility key
            st.session_state["tool6_summary_findings_extracted"] = extracted

            # Save status
            st.session_state[SS_DATA_HASH] = current_hash
            st.session_state[SS_LAST_SAVE_TS] = _now_hhmmss()
            st.session_state[SS_DIRTY] = False
        else:
            # no change
            st.session_state[SS_DIRTY] = False

        # Status
        st.divider()
        extracted_final = st.session_state.get(SS_EXTRACTED, []) or []
        if extracted_final:
            status_card("Saved", f"Valid findings: {len(extracted_final)}", level="success")
        else:
            status_card("Empty", "Please enter at least one finding.", level="warning")

        card_close()

    return len(st.session_state.get(SS_EXTRACTED, []) or []) >= 1
