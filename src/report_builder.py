# src/report_builder.py
from __future__ import annotations

import io
import re
import zipfile
import inspect
from typing import Optional, Dict, Any, List, Callable, Tuple

from docx import Document
from docx.shared import Mm

# ------------------------------------------------------------------
# Core sections
# ------------------------------------------------------------------
from src.report_sections._hf import apply_header_footer
from src.report_sections.cover_page import add_cover_page
from src.report_sections.toc_page import add_toc_page

from src.report_sections.general_project_information import add_general_project_information
from src.report_sections.executive_summary import add_executive_summary
from src.report_sections.data_collection_methods import add_data_collection_methods
from src.report_sections.work_progress_summary import add_work_progress_summary_during_visit

# Observations (Tool6)
from src.report_sections.observations_page import add_observations_page
from src.report_sections.conclusion import add_conclusion_section


# =============================================================================
# Optional import: Section 6 (Summary of Findings)
# =============================================================================
def _import_summary_of_findings_section6():
    """
    Robust import resolver for Section 6:
    Tries common module names so your project won't break if you renamed the file.

    Must expose: add_summary_of_findings_section6(doc, extracted_rows=..., severity_by_no=..., severity_by_finding=..., add_legend=..., ...)
    """
    candidates = [
        ("src.report_sections.summary_of_findings", "add_summary_of_findings_section6"),
        ("src.report_sections.summary_of_the_findings", "add_summary_of_findings_section6"),
        ("src.report_sections.section6_summary_of_findings", "add_summary_of_findings_section6"),
        ("src.report_sections.summary_findings", "add_summary_of_findings_section6"),
    ]
    last_err = None
    for mod_name, fn_name in candidates:
        try:
            mod = __import__(mod_name, fromlist=[fn_name])
            fn = getattr(mod, fn_name)
            if callable(fn):
                return fn
        except Exception as e:
            last_err = e
            continue

    raise ImportError(
        "Cannot import add_summary_of_findings_section6.\n"
        "Expected a module like:\n"
        " - src/report_sections/summary_of_findings.py\n"
        "With a callable function: add_summary_of_findings_section6\n"
        f"Last error: {last_err}"
    )


# =============================================================================
# Tool6 state helpers (single source of truth)
# =============================================================================
def _get_tool6_state_fallback(
    component_observations: Optional[List[Dict[str, Any]]],
    photo_bytes: Optional[Dict[str, bytes]],
) -> Tuple[List[Dict[str, Any]], Dict[str, bytes]]:
    """
    If the caller did not pass Tool6 data explicitly, pull it from Streamlit session_state.

    Guarantees:
      - component_observations: list (never None)
      - photo_bytes: dict (never None)
    """
    try:
        import streamlit as st
    except Exception:
        return component_observations or [], photo_bytes or {}

    if not component_observations:
        component_observations = (
            st.session_state.get("tool6_component_observations_final")
            or st.session_state.get("tool6_obs_components")
            or []
        )

    if not photo_bytes:
        photo_bytes = st.session_state.get("photo_bytes") or {}

    if not isinstance(component_observations, list):
        component_observations = []
    if not isinstance(photo_bytes, dict):
        photo_bytes = {}

    return component_observations, photo_bytes


def _safe_bytes_dict(d: Any) -> Dict[str, bytes]:
    """
    Normalize unknown input into Dict[str, bytes].
    """
    if not isinstance(d, dict):
        return {}
    out: Dict[str, bytes] = {}
    for k, v in d.items():
        if isinstance(k, str) and isinstance(v, (bytes, bytearray)) and v:
            out[k] = bytes(v)
    return out


def _merge_photo_bytes(*sources: Dict[str, bytes]) -> Dict[str, bytes]:
    """
    Merge photo bytes dictionaries (later sources override earlier ones).
    """
    merged: Dict[str, bytes] = {}
    for src in sources:
        if not isinstance(src, dict):
            continue
        for url, b in src.items():
            if isinstance(url, str) and isinstance(b, (bytes, bytearray)) and b:
                merged[url] = bytes(b)
    return merged


def _extract_embedded_photo_bytes_from_components(component_observations: List[Dict[str, Any]]) -> Dict[str, bytes]:
    """
    Extract photo bytes that might be embedded directly in Tool6 structures.

    Supported locations:
      A) Step 3 (recommended):
         comp["observations_valid"][*]["photos"][*] -> {"url": str, "bytes": bytes}
      B) Step 4:
         comp["observations_valid"][*]["major_table"][*] -> {"photo": url, "photo_bytes": bytes}

    Returns:
      Dict[url, bytes]
    """
    out: Dict[str, bytes] = {}
    for comp in component_observations or []:
        if not isinstance(comp, dict):
            continue

        ov = comp.get("observations_valid") or []
        if not isinstance(ov, list):
            continue

        for ob in ov:
            if not isinstance(ob, dict):
                continue

            # A) Step 3 embedded bytes: photos[*]["bytes"]
            photos = ob.get("photos") or []
            if isinstance(photos, list):
                for p in photos:
                    if not isinstance(p, dict):
                        continue
                    url = str(p.get("url") or "").strip()
                    b = p.get("bytes")
                    if url and isinstance(b, (bytes, bytearray)) and b:
                        out[url] = bytes(b)

            # B) Step 4 embedded bytes: major_table[*]["photo_bytes"]
            major = ob.get("major_table") or []
            if isinstance(major, list):
                for row in major:
                    if not isinstance(row, dict):
                        continue
                    url = str(row.get("photo") or "").strip()
                    b = row.get("photo_bytes")
                    if url and isinstance(b, (bytes, bytearray)) and b:
                        out[url] = bytes(b)

    return out


def _inject_photo_bytes_into_major_table(
    component_observations: List[Dict[str, Any]],
    photo_bytes: Dict[str, bytes],
) -> None:
    """
    Ensure each major_table row has 'photo_bytes' if 'photo' URL is set.

    Mutates component_observations in-place.
    """
    if not component_observations or not isinstance(photo_bytes, dict):
        return

    for comp in component_observations:
        if not isinstance(comp, dict):
            continue

        ov = comp.get("observations_valid") or []
        if not isinstance(ov, list):
            continue

        for ob in ov:
            if not isinstance(ob, dict):
                continue

            major = ob.get("major_table") or []
            if not isinstance(major, list):
                continue

            for row in major:
                if not isinstance(row, dict):
                    continue
                url = str(row.get("photo") or "").strip()
                if not url:
                    continue
                if not row.get("photo_bytes"):
                    b = photo_bytes.get(url)
                    if isinstance(b, (bytes, bytearray)) and b:
                        row["photo_bytes"] = bytes(b)


# =============================================================================
# Step 5 (Work progress) helpers
# =============================================================================
def _safe_work_progress_rows(rows: Any) -> List[Dict[str, Any]]:
    """
    Normalize Step 5 rows into List[Dict[str, Any]].
    """
    if not isinstance(rows, list):
        return []

    allowed = {"Activities", "Planned", "Achieved", "Progress", "Remarks", "No."}
    out: List[Dict[str, Any]] = []

    for r in rows:
        if not isinstance(r, dict):
            continue
        cleaned = {k: r.get(k) for k in allowed if k in r}

        act = str(cleaned.get("Activities") or "").strip()
        others = any(str(cleaned.get(k) or "").strip() for k in ("Planned", "Achieved", "Progress", "Remarks"))
        if not act and not others:
            continue

        out.append(cleaned)

    return out


def _get_work_progress_rows_fallback(
    *,
    work_progress_rows: Optional[List[Dict[str, Any]]],
    general_info_overrides: Optional[dict],
) -> List[Dict[str, Any]]:
    """
    Priority:
      1) explicit argument `work_progress_rows`
      2) general_info_overrides["__work_progress_rows__"]
      3) Streamlit session_state["tool6_work_progress_rows"]
    """
    if work_progress_rows is not None:
        return _safe_work_progress_rows(work_progress_rows)

    if isinstance(general_info_overrides, dict) and "__work_progress_rows__" in general_info_overrides:
        return _safe_work_progress_rows(general_info_overrides.get("__work_progress_rows__"))

    try:
        import streamlit as st
        return _safe_work_progress_rows(st.session_state.get("tool6_work_progress_rows"))
    except Exception:
        return []


# =============================================================================
# Step 8 (Summary of Findings) payload helpers
# =============================================================================
def _safe_int_key_dict(d: Any) -> Dict[int, str]:
    if not isinstance(d, dict):
        return {}
    out: Dict[int, str] = {}
    for k, v in d.items():
        try:
            ik = int(k)
        except Exception:
            continue
        sv = str(v).strip() if v is not None else ""
        if sv:
            out[ik] = sv
    return out


def _safe_str_dict(d: Any) -> Dict[str, str]:
    if not isinstance(d, dict):
        return {}
    out: Dict[str, str] = {}
    for k, v in d.items():
        if not isinstance(k, str):
            continue
        sv = str(v).strip() if v is not None else ""
        if sv:
            out[k] = sv
    return out


def _safe_extracted_rows(rows: Any) -> List[Dict[str, str]]:
    """
    Expected: [{"finding": "...", "recommendation": "..."}]
    """
    if not isinstance(rows, list):
        return []
    out: List[Dict[str, str]] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        f = str(r.get("finding") or "").strip()
        if not f:
            continue
        rec = str(r.get("recommendation") or "").strip()
        out.append({"finding": f, "recommendation": rec})
    return out


def _get_summary_findings_payload_fallback(
    *,
    general_info_overrides: Optional[dict],
) -> Tuple[List[Dict[str, str]], Dict[int, str], Dict[str, str], bool]:
    """
    Pull Step 8 outputs for Section 6 printing.

    Priority:
      A) general_info_overrides (if you choose to persist there later)
      B) Streamlit session_state keys from Step 8:
         - tool6_summary_findings_extracted
         - tool6_severity_by_no
         - tool6_severity_by_finding
         - tool6_add_legend
    """
    extracted_rows: List[Dict[str, str]] = []
    sev_by_no: Dict[int, str] = {}
    sev_by_finding: Dict[str, str] = {}
    add_legend = True

    # A) overrides
    if isinstance(general_info_overrides, dict):
        extracted_rows = _safe_extracted_rows(general_info_overrides.get("tool6_summary_findings_extracted"))
        sev_by_no = _safe_int_key_dict(general_info_overrides.get("tool6_severity_by_no"))
        sev_by_finding = _safe_str_dict(general_info_overrides.get("tool6_severity_by_finding"))
        if "tool6_add_legend" in general_info_overrides:
            add_legend = bool(general_info_overrides.get("tool6_add_legend", True))

    # B) session_state fallback (preferred in your current architecture)
    try:
        import streamlit as st

        if not extracted_rows:
            extracted_rows = _safe_extracted_rows(st.session_state.get("tool6_summary_findings_extracted"))

        if not sev_by_no:
            sev_by_no = _safe_int_key_dict(st.session_state.get("tool6_severity_by_no"))

        if not sev_by_finding:
            sev_by_finding = _safe_str_dict(st.session_state.get("tool6_severity_by_finding"))

        if "tool6_add_legend" in st.session_state:
            add_legend = bool(st.session_state.get("tool6_add_legend", True))

    except Exception:
        pass

    return extracted_rows, sev_by_no, sev_by_finding, add_legend


# =============================================================================
# Page / Word utilities
# =============================================================================
def set_page_a4(section) -> None:
    section.page_width = Mm(210)
    section.page_height = Mm(297)

    section.top_margin = Mm(12.7)
    section.bottom_margin = Mm(12.7)
    section.left_margin = Mm(12.5)
    section.right_margin = Mm(12.5)

    section.header_distance = Mm(5)
    section.footer_distance = Mm(5)


def strip_heading_numbering(text: Any) -> str:
    t = "" if text is None else str(text).strip()
    if not t:
        return ""
    t = re.sub(r"^\s*\(?\d+(\.\d+)*\)?\s*[\.\)\-:]\s*", "", t)
    t = re.sub(r"^\s*\d+(\.\d+)*\s+", "", t)
    return t.strip()


def update_docx_fields_bytes(docx_bytes: bytes) -> bytes:
    if not docx_bytes:
        return docx_bytes

    zin = zipfile.ZipFile(io.BytesIO(docx_bytes), "r")
    file_map = {n: zin.read(n) for n in zin.namelist()}
    zin.close()

    name = "word/settings.xml"
    xml = file_map.get(name)
    if not xml:
        return docx_bytes

    txt = xml.decode("utf-8", errors="ignore")
    if "w:updateFields" not in txt:
        txt = txt.replace("</w:settings>", '<w:updateFields w:val="true"/></w:settings>')

    file_map[name] = txt.encode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for k, v in file_map.items():
            zout.writestr(k, v)

    return out.getvalue()


def _doc_to_bytes(doc: Document) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# =============================================================================
# Robust compatibility caller
# =============================================================================
def _call_compat(fn: Callable, *args, **kwargs):
    """
    Call functions safely even if signature differs (older/newer versions).
    """
    try:
        return fn(*args, **kwargs)
    except TypeError:
        sig = inspect.signature(fn)
        accepted = sig.parameters.keys()
        filtered = {k: v for k, v in kwargs.items() if k in accepted}
        # Keep args but avoid passing too many
        return fn(*args[: len(accepted)], **filtered)


# =============================================================================
# Base document builder (Cover + TOC)
# =============================================================================
def _build_base_doc(
    *,
    row: Dict[str, Any],
    cover_image_bytes: Optional[bytes],
    general_info_overrides: Optional[dict],
    reserved_mm: int,
    unicef_logo_path: Optional[str],
    act_logo_path: Optional[str],
    ppc_logo_path: Optional[str],
    toc_levels: str,
) -> Document:
    doc = Document()
    set_page_a4(doc.sections[0])

    apply_header_footer(
        doc,
        unicef_logo_path=unicef_logo_path,
        act_logo_path=act_logo_path,
        ppc_logo_path=ppc_logo_path,
    )

    _call_compat(
        add_cover_page,
        doc,
        row,
        cover_image_bytes,
        general_info_overrides=general_info_overrides,
        reserved_mm=reserved_mm,
    )

    add_toc_page(
        doc,
        toc_levels=toc_levels,
        include_hyperlinks=True,
        hide_page_numbers_in_web_layout=False,
    )

    return doc


# =============================================================================
# Helpers: activity titles extraction (better alignment with Step 3/5)
# =============================================================================
def _extract_activity_titles_from_component_observations(component_observations: List[Dict[str, Any]]) -> List[str]:
    """
    Prefer extracting titles from observations_valid[*].title (these are the real "activities" titles).
    Deduplicate while preserving order.
    """
    titles: List[str] = []
    for comp in component_observations or []:
        if not isinstance(comp, dict):
            continue
        ov = comp.get("observations_valid") or []
        if not isinstance(ov, list):
            continue
        for ob in ov:
            if not isinstance(ob, dict):
                continue
            t = strip_heading_numbering(ob.get("title"))
            if t:
                titles.append(t)

    # de-dup keep order
    seen = set()
    out: List[str] = []
    for t in titles:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


# =============================================================================
# MAIN PUBLIC API — Tool6 Full Report
# =============================================================================
def build_tool6_full_report_docx(
    *,
    row: Dict[str, Any],
    cover_image_bytes: Optional[bytes] = None,
    general_info_overrides: Optional[dict] = None,
    component_observations: Optional[List[Dict[str, Any]]] = None,
    photo_bytes: Optional[Dict[str, bytes]] = None,
    work_progress_rows: Optional[List[Dict[str, Any]]] = None,
    reserved_mm: int = 165,
    unicef_logo_path: Optional[str] = None,
    act_logo_path: Optional[str] = None,
    ppc_logo_path: Optional[str] = None,
    conclusion_text: Optional[str] = None,
    conclusion_key_points: Optional[List[str]] = None,
    conclusion_recommendations_summary: Optional[str] = None,
    conclusion_section_no: str = "7",
    **_,
) -> bytes:
    # ------------------------------------------------------------------
    # Guaranteed Tool6 data
    # ------------------------------------------------------------------
    component_observations, photo_bytes = _get_tool6_state_fallback(component_observations, photo_bytes)

    if not component_observations:
        raise RuntimeError(
            "Tool6 report generation failed: component_observations is empty.\n"
            "Step 3 / Step 4 data was not persisted in session_state."
        )

    general_info_overrides = general_info_overrides or {}

    # ------------------------------------------------------------------
    # Step 5 rows
    # ------------------------------------------------------------------
    wp_rows = _get_work_progress_rows_fallback(
        work_progress_rows=work_progress_rows,
        general_info_overrides=general_info_overrides,
    )
    general_info_overrides["__work_progress_rows__"] = wp_rows

    # ------------------------------------------------------------------
    # Step 8 rows (Summary of Findings -> Section 6)
    # ------------------------------------------------------------------
    extracted_rows, severity_by_no, severity_by_finding, add_legend = _get_summary_findings_payload_fallback(
        general_info_overrides=general_info_overrides
    )
    # Optionally persist (helps later sections that rely on overrides)
    general_info_overrides["tool6_summary_findings_extracted"] = extracted_rows
    general_info_overrides["tool6_severity_by_no"] = severity_by_no
    general_info_overrides["tool6_severity_by_finding"] = severity_by_finding
    general_info_overrides["tool6_add_legend"] = bool(add_legend)

    # ------------------------------------------------------------------
    # Photo bytes (robust merge)
    # ------------------------------------------------------------------
    photo_bytes_in = _safe_bytes_dict(photo_bytes)
    embedded_bytes = _extract_embedded_photo_bytes_from_components(component_observations)

    try:
        import streamlit as st
        cache_bytes = _safe_bytes_dict(st.session_state.get("photo_bytes") or {})
    except Exception:
        cache_bytes = {}

    photo_bytes_final = _merge_photo_bytes(embedded_bytes, photo_bytes_in, cache_bytes)
    _inject_photo_bytes_into_major_table(component_observations, photo_bytes_final)

    # ------------------------------------------------------------------
    # Base doc
    # ------------------------------------------------------------------
    doc = _build_base_doc(
        row=row,
        cover_image_bytes=cover_image_bytes,
        general_info_overrides=general_info_overrides,
        reserved_mm=reserved_mm,
        unicef_logo_path=unicef_logo_path,
        act_logo_path=act_logo_path,
        ppc_logo_path=ppc_logo_path,
        toc_levels="1-3",
    )

    # ------------------------------------------------------------------
    # Sections 1–3
    # ------------------------------------------------------------------
    _call_compat(add_general_project_information, doc, row=row, overrides=general_info_overrides)
    _call_compat(add_executive_summary, doc, row=row, overrides=general_info_overrides)
    _call_compat(add_data_collection_methods, doc, row=row, overrides=general_info_overrides)

    # ------------------------------------------------------------------
    # Section 4 — Work Progress Summary
    # ------------------------------------------------------------------
    activity_titles = _extract_activity_titles_from_component_observations(component_observations)
    rows_for_docx = wp_rows if wp_rows else None

    _call_compat(
        add_work_progress_summary_during_visit,
        doc,
        activity_titles_from_section5=activity_titles,
        title_text="4.    Work Progress Summary during the Visit.",
        rows=rows_for_docx,
    )

    # ------------------------------------------------------------------
    # Section 5 — Observations (Major findings + Recommendations inside)
    # ------------------------------------------------------------------
    _call_compat(
        add_observations_page,
        doc,
        component_observations=component_observations,
        photo_bytes=photo_bytes_final,
        include_findings_recommendations=True,  # if your observations_page supports it
    )

    # ------------------------------------------------------------------
    # ✅ Section 6 — Summary of the findings (from Step 8)
    # ------------------------------------------------------------------
    add_summary_of_findings_section6 = _import_summary_of_findings_section6()

    _call_compat(
        add_summary_of_findings_section6,
        doc,
        extracted_rows=extracted_rows,
        severity_by_no=severity_by_no,
        severity_by_finding=severity_by_finding,
        add_legend=bool(add_legend),
        add_page_break_before=True,
    )

    # ------------------------------------------------------------------
    # Section 7 — Conclusion
    # ------------------------------------------------------------------
    _call_compat(
        add_conclusion_section,
        doc,
        conclusion_text=conclusion_text,
        key_points=conclusion_key_points,
        recommendations_summary=conclusion_recommendations_summary,
        section_no=conclusion_section_no,
    )

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------
    return update_docx_fields_bytes(_doc_to_bytes(doc))
