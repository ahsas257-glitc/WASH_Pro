from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Tuple, Optional

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


# =============================================================================
# Small helpers (fast + safe)
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"t6.s8.{h}"


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
    # remove leading bullet markers
    t = re.sub(r"^[•\-\–\—\*]+\s*", "", t).strip()
    # remove extra punctuation at ends
    t = t.strip(" .;:,-")
    return t


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

    # Keep only the first sentence-ish part for title
    f = re.split(r"[.!?]\s+", f, maxsplit=1)[0].strip()
    f = re.sub(r"\([^)]*\)", "", f).strip()  # drop parentheses content for brevity

    # Token filtering to keep signal words
    tokens = [t for t in re.split(r"[^\w]+", f) if t]
    kept: List[str] = []
    for t in tokens:
        tl = t.lower()
        if tl in STOPWORDS:
            continue
        if len(t) <= 1:
            continue
        kept.append(t)

    # If we over-filtered, fallback to raw
    core = " ".join(kept) if kept else f
    core = _clamp_words(core, 10)
    core = core.strip(" .;:,-")

    # Gentle capitalization
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
    hi = _score_patterns(text, HIGH_PATTERNS)
    med = _score_patterns(text, MED_PATTERNS)
    lo = _score_patterns(text, LOW_PATTERNS)

    # Strong High triggers
    if hi >= 1 and ("immediate" in text.lower() or "unsafe" in text.lower() or "not functional" in text.lower()):
        return "High"

    # If high has clear presence and outweighs medium
    if hi >= 2 and hi >= med:
        return "High"

    # Medium logic
    if med >= 1:
        # if we only saw "leak" but no strong high indicators, medium
        return "Medium"

    # Low logic
    if lo >= 1:
        return "Low"

    # Default safe choice
    return "Medium"


# =============================================================================
# 3) Recommendation summarizer (short + logical)
# =============================================================================
def _summarize_reco(recos: List[str], fallback: str = "") -> str:
    """
    Turn a list of recommendations into 1–2 short sentences.
    Limits length for report cleanliness.
    """
    items = [_clean_for_title(x) for x in (recos or []) if _clean_for_title(x)]
    if not items and _clean_for_title(fallback):
        items = [_clean_for_title(fallback)]

    if not items:
        return "—"

    # De-duplicate (case-insensitive)
    seen = set()
    uniq: List[str] = []
    for it in items:
        key = it.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    # Keep top 2 items for summary
    top = uniq[:2]
    # Make short
    top = [_clamp_words(x, 18).strip(" .;:,-") for x in top if x]

    out = " ".join([_norm_sentence(x) for x in top if x]).strip()
    if not out:
        return "—"

    # Hard cap to avoid ugly wrapping
    if len(out) > 240:
        out = out[:237].rstrip() + "..."
    return out


# =============================================================================
# Section 5 fingerprint & extraction
# =============================================================================
def _fp_section5(component_observations: Any) -> str:
    """
    Fast + reliable fingerprint:
    Uses titles + finding texts + recommendations count, but keeps it light.
    """
    if not isinstance(component_observations, list) or not component_observations:
        return "empty"

    pieces: List[str] = []
    try:
        for comp in component_observations[:12]:  # cap to keep it fast
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
    """
    Your current pipeline:
    comp -> observations_valid -> (major_table findings, recommendations list)
    Return list of dicts including component + finding + recos.
    """
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
                # Fallback: if no major_table but there are recommendations
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
    """
    Auto-generate rows (editable by user).
    """
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
    """
    Outputs:
      - extracted list for DOC section: [{"finding":..., "recommendation":...}]
      - severity_by_no: {1:"High", ...}
      - severity_by_finding: {"finding text": "High", ...}
    """
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

    fp = _fp_section5(component_observations)

    # First time
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


# =============================================================================
# Main renderer
# =============================================================================
def render_step(ctx: Tool6Context, *, title: str = "Step 8 — Summary of Findings") -> bool:
    if pd is None:
        st.error("pandas is required for Step 8. Please install pandas.")
        return False

    st.subheader(title)
    st.caption("Auto-generated from Section 5. You can edit findings, severity, and recommendations. Changes save instantly.")

    # Source: merged observations (preferred)
    component_observations = st.session_state.get("tool6_component_observations_final")
    if component_observations is None:
        component_observations = st.session_state.get("component_observations", [])

    if not isinstance(component_observations, list):
        component_observations = []

    _ensure_state(component_observations)

    with st.container(border=True):
        card_open(
            "Summary of the findings",
            subtitle="Auto-generated from Step 3/4 (Section 5). You can edit severity and recommendations here.",
            variant="lg-variant-cyan",
        )

        # Toolbar
        colA, colB, colC = st.columns([1, 1, 2], vertical_alignment="center")
        with colA:
            st.session_state[SS_LOCK] = st.toggle(
                "Confirmed",
                value=bool(st.session_state.get(SS_LOCK, False)),
                key=_key("confirm_lock"),
                help="If ON, this step will not auto-refresh when Section 5 changes.",
            )
        with colB:
            if st.button("Auto-generate from Section 5", use_container_width=True, key=_key("reset")):
                st.session_state[SS_ROWS] = _default_rows(component_observations)
                st.session_state[SS_SOURCE_FP] = _fp_section5(component_observations)
                st.session_state[SS_LOCK] = False
                st.rerun()
        with colC:
            st.session_state[SS_ADD_LEGEND] = st.toggle(
                "Add severity legend in report",
                value=bool(st.session_state.get(SS_ADD_LEGEND, True)),
                key=_key("legend"),
            )

        rows = st.session_state.get(SS_ROWS) or []
        for i, r in enumerate(rows, start=1):
            if isinstance(r, dict):
                r["No."] = str(i)

        df = pd.DataFrame(rows, columns=["No.", "Finding", "Severity", "Recommendation / Corrective Action"])

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

        # Autosave
        new_rows: List[Dict[str, str]] = []
        for _, r in edited_df.iterrows():
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

        # Store outputs for report builder / step10
        st.session_state[SS_SEVERITY_BY_NO] = sev_by_no
        st.session_state[SS_SEVERITY_BY_FINDING] = sev_by_finding
        st.session_state[SS_EXTRACTED] = extracted

        # Optional compatibility: some builders read these keys
        st.session_state["tool6_summary_findings_extracted"] = extracted

        # Status
        st.divider()
        if extracted:
            status_card("Saved", f"Valid findings: {len(extracted)}", level="success")
        else:
            status_card("Empty", "Please enter at least one finding.", level="warning")

        card_close()

    return len(st.session_state.get(SS_EXTRACTED, []) or []) >= 1
