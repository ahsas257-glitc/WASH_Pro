from __future__ import annotations

import os
import tempfile
import hashlib
from io import BytesIO
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List

import streamlit as st
from PIL import Image
from docx import Document

from src.Tools.utils.types import Tool6Context
from src.report_sections.cover_page import add_cover_page
from design.components.base_tool_ui import card_open, card_close, status_card

# ============================================================
# Session keys (Step 1 only)
# ============================================================
SS_COVER_OVERRIDES = "cover_table_overrides"     # dict of cover-table values
SS_COVER_DATE_FMT = "cover_date_format"          # selected date format (strftime OR label)
SS_COVER_UPLOAD_BYTES = "cover_upload_bytes"     # uploaded cover bytes

SS_PHOTO_SELECTIONS = "photo_selections"
SS_PHOTO_BYTES = "photo_bytes"
SS_PHOTO_FIELD = "photo_field"

# (performance helpers)
SS_COVER_SELECTED_URL = "Tools_cover_selected_url"
SS_PREVIEW_DOCX_HASH = "Tools_cover_preview_docx_hash"
SS_PREVIEW_DOCX_BYTES = "Tools_cover_preview_docx_bytes"
SS_PREVIEW_PNG_HASH = "Tools_cover_preview_png_hash"
SS_PREVIEW_PNG_BYTES = "Tools_cover_preview_png_bytes"


# ============================================================
# Cover table fields (ONLY the cover table)
# ============================================================
COVER_FIELDS: List[Tuple[str, str]] = [
    ("Project Title:", "Project Title"),
    ("Visit No.:", "Visit No."),
    ("Type of Intervention:", "Type of Intervention"),
    ("Province / District / Village:", "Province / District / Village"),
    ("Date of Visit:", "Date of Visit"),
    ("Implementing Partner (IP):", "Implementing Partner (IP)"),
    ("Prepared by:", "Prepared by"),
    ("Prepared for:", "Prepared for"),
]

DEFAULT_PREPARED_BY = "Premium Performance Consulting (PPC) & Act for Performance"
DEFAULT_PREPARED_FOR = "UNICEF"


# ============================================================
# Date format options (user-selectable)
# ============================================================
DATE_FORMATS: List[Tuple[str, str]] = [
    ("DD/Mon/YYYY  (21/Jan/2026)", "%d/%b/%Y"),
    ("DD/Month/YYYY (21/January/2026)", "%d/%B/%Y"),
    ("DD-Mon-YYYY  (21-Jan-2026)", "%d-%b-%Y"),
    ("DD-Month-YYYY (21-January-2026)", "%d-%B-%Y"),
    ("YYYY-MM-DD (2026-01-21)", "%Y-%m-%d"),
    ("DD/MM/YYYY (21/01/2026)", "%d/%m/%Y"),
    ("DD/MM/YY (21/01/26)", "%d/%m/%y"),
    ("DD Mon YYYY (21 Jan 2026)", "%d %b %Y"),
    ("DD Month YYYY (21 January 2026)", "%d %B %Y"),
]


# ============================================================
# Helpers
# ============================================================
def s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def enforce_single_cover(selections: Dict[str, str]) -> Dict[str, str]:
    selections = selections or {}
    covers = [u for u, p in selections.items() if p == "Cover Page"]
    if len(covers) <= 1:
        return selections
    keep = covers[-1]
    for u in covers[:-1]:
        selections[u] = "Not selected"
    selections[keep] = "Cover Page"
    return selections


def _to_clean_png_bytes(img_bytes: bytes) -> bytes:
    img = Image.open(BytesIO(img_bytes)).convert("RGB")
    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _parse_isoish_date(value: Any) -> Optional[datetime]:
    sv = s(value)
    if not sv:
        return None
    sv = sv.split(".")[0].replace("T", " ").replace("Z", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(sv, fmt)
        except Exception:
            pass
    return None


def _format_visit_date(raw_date: Any, fmt: str) -> str:
    dt = _parse_isoish_date(raw_date)
    if not dt:
        sv = s(raw_date)
        return sv.split(" ")[0] if " " in sv else sv
    try:
        return dt.strftime(fmt)
    except Exception:
        return dt.strftime("%d/%b/%Y")


def _build_cover_defaults(ctx: Tool6Context) -> Dict[str, str]:
    row = ctx.row or {}
    defaults = ctx.defaults or {}

    province = s(defaults.get("Province", "")) or s(row.get("A01_Province"))
    district = s(defaults.get("District", "")) or s(row.get("A02_District"))
    village = s(defaults.get("Village / Community", "")) or s(row.get("Village"))
    location = ", ".join([x for x in [province, district, village] if x])

    project_title = s(
        row.get("Activity_Name")
        or defaults.get("Project Name")
        or defaults.get("Project Title")
        or ""
    )

    visit_no = s(row.get("A26_Visit_number") or defaults.get("Visit No") or defaults.get("Visit No.") or "1")

    Tools_name = s(
        row.get("Tools_Name")
        or row.get("Tools")
        or defaults.get("Tools Name")
        or defaults.get("Type of Intervention")
        or "Solar Water Supply"
    )

    starttime = row.get("starttime") or defaults.get("Date of Visit") or ""
    fmt = st.session_state.get(SS_COVER_DATE_FMT, "%d/%b/%Y")
    date_formatted = _format_visit_date(starttime, fmt) if starttime else ""

    ip = s(
        row.get("Primary_Partner_Name")
        or defaults.get("Name of the IP, Organization / NGO")
        or ""
    )

    return {
        "Project Title": project_title,
        "Visit No.": visit_no,
        "Type of Intervention": Tools_name,
        "Province / District / Village": location,
        "Date of Visit": date_formatted,
        "Implementing Partner (IP)": ip,
        "Prepared by": DEFAULT_PREPARED_BY,
        "Prepared for": DEFAULT_PREPARED_FOR,
    }


def _ensure_cover_state(ctx: Tool6Context) -> None:
    st.session_state.setdefault(SS_PHOTO_SELECTIONS, {})
    st.session_state.setdefault(SS_PHOTO_BYTES, {})
    st.session_state.setdefault(SS_PHOTO_FIELD, {})
    st.session_state.setdefault(SS_COVER_UPLOAD_BYTES, None)
    st.session_state.setdefault(SS_COVER_DATE_FMT, "%d/%b/%Y")
    st.session_state.setdefault(SS_COVER_SELECTED_URL, None)

    if SS_COVER_OVERRIDES not in st.session_state or not isinstance(st.session_state[SS_COVER_OVERRIDES], dict):
        st.session_state[SS_COVER_OVERRIDES] = _build_cover_defaults(ctx)
    else:
        d = st.session_state[SS_COVER_OVERRIDES]
        defaults = _build_cover_defaults(ctx)
        for k, v in defaults.items():
            d.setdefault(k, v)
        st.session_state[SS_COVER_OVERRIDES] = d


def resolve_cover_bytes() -> Optional[bytes]:
    selections = st.session_state.get(SS_PHOTO_SELECTIONS, {})
    photo_bytes = st.session_state.get(SS_PHOTO_BYTES, {})

    cover_urls = [u for u, p in (selections or {}).items() if p == "Cover Page"]
    cover_bytes = photo_bytes.get(cover_urls[0]) if cover_urls else None

    if cover_bytes is None and st.session_state.get(SS_COVER_UPLOAD_BYTES) is not None:
        cover_bytes = st.session_state[SS_COVER_UPLOAD_BYTES]

    return cover_bytes


def _build_cover_preview_docx_bytes(
    ctx: Tool6Context,
    *,
    cover_image_bytes: Optional[bytes],
    cover_table_values: Dict[str, str],
) -> bytes:
    row = ctx.row or {}
    doc = Document()

    loc = s(cover_table_values.get("Province / District / Village"))
    parts = [p.strip() for p in loc.split(",")] if loc else []
    province = parts[0] if len(parts) > 0 else s(row.get("A01_Province"))
    district = parts[1] if len(parts) > 1 else s(row.get("A02_District"))
    village = parts[2] if len(parts) > 2 else s(row.get("Village"))

    ovr = {
        "Activity_Name": s(cover_table_values.get("Project Title")),
        "A26_Visit_number": s(cover_table_values.get("Visit No.")),
        "Tools_Name": s(cover_table_values.get("Type of Intervention")),
        "A01_Province": province,
        "A02_District": district,
        "Village": village,
        "starttime": s(cover_table_values.get("Date of Visit")),
        "Primary_Partner_Name": s(cover_table_values.get("Implementing Partner (IP)")),
        "Prepared by": s(cover_table_values.get("Prepared by")),
        "Prepared for": s(cover_table_values.get("Prepared for")),
    }

    add_cover_page(doc, row, cover_image_bytes, general_info_overrides=ovr)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _docx_first_page_to_png(docx_bytes: bytes) -> Optional[bytes]:
    """
    Windows + MS Word required.
    Requires: pywin32 + pymupdf.
    """
    try:
        import pythoncom
        import win32com.client
        import fitz
    except Exception:
        return None

    with tempfile.TemporaryDirectory() as td:
        docx_path = os.path.join(td, "preview.docx")
        pdf_path = os.path.join(td, "preview.pdf")

        with open(docx_path, "wb") as f:
            f.write(docx_bytes)

        pythoncom.CoInitialize()
        word = None
        doc = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0

            doc = word.Documents.Open(
                docx_path,
                ReadOnly=True,
                AddToRecentFiles=False,
                ConfirmConversions=False,
                NoEncodingDialog=True,
            )

            # 17 = wdFormatPDF
            # SaveAs2 tends to be more stable, but SaveAs is okay too.
            try:
                doc.SaveAs2(pdf_path, FileFormat=17)
            except Exception:
                doc.SaveAs(pdf_path, FileFormat=17)

            doc.Close(False)
            doc = None
        finally:
            try:
                if doc is not None:
                    doc.Close(False)
            except Exception:
                pass
            try:
                if word is not None:
                    word.Quit()
            except Exception:
                pass
            pythoncom.CoUninitialize()

        try:
            pdf = fitz.open(pdf_path)
            if pdf.page_count < 1:
                return None
            page = pdf.load_page(0)
            pix = page.get_pixmap(dpi=170)
            out = pix.tobytes("png")
            pdf.close()
            return out
        except Exception:
            return None


def _get_or_build_preview_docx(ctx: Tool6Context, cover_img: bytes, table_vals: Dict[str, str]) -> Optional[bytes]:
    """
    Cache DOCX bytes by a stable hash:
      - cover image hash
      - table values
      - current cover date fmt (already reflected in table date)
    """
    if not cover_img:
        return None

    # stable fingerprint
    table_items = tuple(sorted((k, s(v)) for k, v in (table_vals or {}).items()))
    fp = repr(( _sha1(cover_img), table_items )).encode("utf-8")
    h = _sha1(fp)

    if st.session_state.get(SS_PREVIEW_DOCX_HASH) == h and st.session_state.get(SS_PREVIEW_DOCX_BYTES):
        return st.session_state[SS_PREVIEW_DOCX_BYTES]

    try:
        docx_bytes = _build_cover_preview_docx_bytes(
            ctx,
            cover_image_bytes=cover_img,
            cover_table_values=table_vals,
        )
    except Exception:
        return None

    st.session_state[SS_PREVIEW_DOCX_HASH] = h
    st.session_state[SS_PREVIEW_DOCX_BYTES] = docx_bytes
    # invalidate png cache (new docx)
    st.session_state[SS_PREVIEW_PNG_HASH] = None
    st.session_state[SS_PREVIEW_PNG_BYTES] = None
    return docx_bytes


def _get_or_build_preview_png(docx_bytes: bytes) -> Optional[bytes]:
    if not docx_bytes:
        return None

    h = _sha1(docx_bytes)
    if st.session_state.get(SS_PREVIEW_PNG_HASH) == h and st.session_state.get(SS_PREVIEW_PNG_BYTES):
        return st.session_state[SS_PREVIEW_PNG_BYTES]

    png = _docx_first_page_to_png(docx_bytes)
    if png:
        st.session_state[SS_PREVIEW_PNG_HASH] = h
        st.session_state[SS_PREVIEW_PNG_BYTES] = png
    return png


# ============================================================
# MAIN RENDER
# ============================================================
def render_step(ctx: Tool6Context, *, fetch_image) -> bool:
    """
    Step 1 UI:
      - cover image select OR upload
      - show cover table, optional edit
      - date format options
      - preview: Word rendered image if available
    Returns True if cover photo exists (to allow Next).
    """
    _ensure_cover_state(ctx)
    cover_table: Dict[str, str] = st.session_state[SS_COVER_OVERRIDES]

    box = st.container(border=True)
    with box:
        card_open(
            "Cover Page",
            subtitle="Select/upload a cover image, optionally edit the cover table, then preview as in Word.",
            variant="lg-variant-cyan",
        )

        # ------------------------------------------------
        # A) Cover image
        # ------------------------------------------------
        col1, col2 = st.columns([1.25, 1], gap="large")

        with col1:
            st.markdown("### 1) Choose cover image (from links)")

            if not getattr(ctx, "all_photo_urls", None):
                status_card("No photos found", "No image URLs detected for this TPM ID.", level="warning")
            else:
                # keep selection stable
                default_url = st.session_state.get(SS_COVER_SELECTED_URL) or ctx.all_photo_urls[0]
                if default_url not in ctx.all_photo_urls:
                    default_url = ctx.all_photo_urls[0]

                selected_url = st.selectbox(
                    "Cover image from SurveyCTO/Sheet",
                    options=ctx.all_photo_urls,
                    index=ctx.all_photo_urls.index(default_url),
                    format_func=lambda u: ctx.photo_label_by_url.get(u, u),
                    key="Tools_cover_pick",
                )
                st.session_state[SS_COVER_SELECTED_URL] = selected_url

                st.session_state[SS_PHOTO_FIELD][selected_url] = ctx.photo_label_by_url.get(selected_url, "Cover Photo")

                # fetch only if not already cached
                cached = st.session_state[SS_PHOTO_BYTES].get(selected_url)
                if cached:
                    st.image(cached, use_container_width=True)
                    st.session_state[SS_PHOTO_SELECTIONS][selected_url] = "Cover Page"
                    st.session_state[SS_PHOTO_SELECTIONS] = enforce_single_cover(st.session_state[SS_PHOTO_SELECTIONS])
                    status_card("Cover selected", "This image will be used on the cover page.", level="success")
                else:
                    ok, data, msg = fetch_image(selected_url)
                    if ok and data:
                        st.image(data, use_container_width=True)
                        st.session_state[SS_PHOTO_BYTES][selected_url] = data
                        st.session_state[SS_PHOTO_SELECTIONS][selected_url] = "Cover Page"
                        st.session_state[SS_PHOTO_SELECTIONS] = enforce_single_cover(st.session_state[SS_PHOTO_SELECTIONS])
                        status_card("Cover selected", "This image will be used on the cover page.", level="success")
                    else:
                        status_card("Failed to load cover", msg or "Unknown error.", level="error")

        with col2:
            st.markdown("### 2) Or upload from PC (optional)")
            up = st.file_uploader(
                "Upload cover image",
                type=["jpg", "jpeg", "png"],
                key="Tools_cover_upload",
                help="If you upload here, it will be used when no online cover is selected.",
            )
            if up:
                b = up.read()
                try:
                    b = _to_clean_png_bytes(b)
                except Exception:
                    pass
                st.session_state[SS_COVER_UPLOAD_BYTES] = b
                st.image(b, use_container_width=True)
                status_card("Uploaded cover saved", "Uploaded image is ready for the cover.", level="success")

        st.divider()

        # ------------------------------------------------
        # B) Cover table (ONLY) + date format options
        # ------------------------------------------------
        st.markdown("### Cover Table (optional)")

        fmt_labels = [x[0] for x in DATE_FORMATS]
        fmt_map = {lbl: fmt for (lbl, fmt) in DATE_FORMATS}
        current_fmt = st.session_state.get(SS_COVER_DATE_FMT, "%d/%b/%Y")
        current_label = next((lbl for (lbl, fmt) in DATE_FORMATS if fmt == current_fmt), fmt_labels[0])

        picked_label = st.selectbox(
            "Date of Visit format",
            fmt_labels,
            index=fmt_labels.index(current_label),
            key="Tools_cover_date_format",
        )
        st.session_state[SS_COVER_DATE_FMT] = fmt_map[picked_label]

        # Auto-update date based on starttime (best-effort)
        raw_starttime = (ctx.row or {}).get("starttime")
        if raw_starttime:
            cover_table["Date of Visit"] = _format_visit_date(raw_starttime, st.session_state[SS_COVER_DATE_FMT])

        show_edit = st.toggle("Edit cover table", value=False, key="Tools_cover_edit_toggle")

        if not show_edit:
            for label, key in COVER_FIELDS:
                st.write(f"**{label}** {s(cover_table.get(key, ''))}")
        else:
            with st.form("Tools_cover_table_form", clear_on_submit=False):
                cA, cB = st.columns([1, 1], gap="large")

                with cA:
                    cover_table["Project Title"] = st.text_area(
                        "Project Title",
                        value=s(cover_table.get("Project Title")),
                        height=70,
                        key="Tools_cover_project_title",
                    )
                    cover_table["Visit No."] = st.text_input(
                        "Visit No.",
                        value=s(cover_table.get("Visit No.")),
                        key="Tools_cover_visit_no",
                    )
                    cover_table["Type of Intervention"] = st.text_input(
                        "Type of Intervention",
                        value=s(cover_table.get("Type of Intervention")),
                        key="Tools_cover_intervention",
                    )
                    cover_table["Date of Visit"] = st.text_input(
                        "Date of Visit",
                        value=s(cover_table.get("Date of Visit")),
                        help="You can override the formatted date manually if needed.",
                        key="Tools_cover_date_manual",
                    )

                with cB:
                    cover_table["Province / District / Village"] = st.text_area(
                        "Province / District / Village",
                        value=s(cover_table.get("Province / District / Village")),
                        height=70,
                        key="Tools_cover_location",
                    )
                    cover_table["Implementing Partner (IP)"] = st.text_area(
                        "Implementing Partner (IP)",
                        value=s(cover_table.get("Implementing Partner (IP)")),
                        height=70,
                        key="Tools_cover_ip",
                    )
                    cover_table["Prepared by"] = st.text_input(
                        "Prepared by",
                        value=s(cover_table.get("Prepared by")) or DEFAULT_PREPARED_BY,
                        key="Tools_cover_prepared_by",
                    )
                    cover_table["Prepared for"] = st.text_input(
                        "Prepared for",
                        value=s(cover_table.get("Prepared for")) or DEFAULT_PREPARED_FOR,
                        key="Tools_cover_prepared_for",
                    )

                save = st.form_submit_button("Save cover table")
                if save:
                    st.session_state[SS_COVER_OVERRIDES] = dict(cover_table)
                    status_card("Saved", "Cover table updated successfully.", level="success")

        st.divider()

        # ------------------------------------------------
        # C) Preview (Word-like) - cached, fast
        # ------------------------------------------------
        st.markdown("### Preview (like Word cover page)")

        cover_bytes = resolve_cover_bytes()
        if cover_bytes is None:
            status_card("No cover image yet", "Please select or upload a cover image to enable preview.", level="warning")
        else:
            docx_preview = _get_or_build_preview_docx(ctx, cover_bytes, st.session_state[SS_COVER_OVERRIDES])
            if not docx_preview:
                status_card("Preview failed", "Could not build preview DOCX.", level="error")
            else:
                # Try Word-rendered PNG (cached)
                png = _get_or_build_preview_png(docx_preview)
                if png:
                    st.image(png, use_container_width=False, caption="Cover page preview (rendered from DOCX)")
                else:
                    st.info(
                        "Exact Word-like preview inside Streamlit requires Microsoft Word + pywin32 + pymupdf.\n"
                        "You can still download the DOCX preview below."
                    )

                st.download_button(
                    "Download Cover Preview (DOCX)",
                    data=docx_preview,
                    file_name=f"Tools_CoverPreview_{ctx.tpm_id}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )

        card_close()

    return resolve_cover_bytes() is not None
