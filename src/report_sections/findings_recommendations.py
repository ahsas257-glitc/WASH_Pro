from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from docx.document import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from PIL import Image


# -------------------------------------------------
# Column widths (INCH) — EXACT LIKE SAMPLE
# -------------------------------------------------
COL_NO = 0.38
COL_FIND = 2.88
COL_COMP = 0.91
COL_PHOTO = 3.40

# -------------------------------------------------
# Border thickness: 1/4 pt
# Word uses eighths of a point for w:sz:
# 0.25pt * 8 = 2
# -------------------------------------------------
BORDER_SZ_EIGHTHS = "2"  # ✅ EXACT 1/4pt


# -------------------------------------------------
# Utils
# -------------------------------------------------
def s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _compact(p) -> None:
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0


def _one_line_gap(doc: Document) -> None:
    """Exactly one blank line (compact) between blocks."""
    p = doc.add_paragraph("")
    _compact(p)


def _clean_png(b: bytes) -> Optional[bytes]:
    """
    Normalize image bytes -> PNG (RGB) to avoid docx image issues.
    Keeps it stable for Word rendering.
    """
    try:
        img = Image.open(io.BytesIO(b))

        # Convert to RGB to avoid alpha-channel issues in some Word setups
        img = img.convert("RGB")

        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _set_table_fixed_layout(tbl) -> None:
    """Prevent Word from auto-resizing columns."""
    tbl.autofit = False
    tblPr = tbl._tbl.tblPr
    tblLayout = tblPr.find(qn("w:tblLayout"))
    if tblLayout is None:
        tblLayout = OxmlElement("w:tblLayout")
        tblPr.append(tblLayout)
    tblLayout.set(qn("w:type"), "fixed")


def _set_table_black_borders(tbl, *, size: str = BORDER_SZ_EIGHTHS) -> None:
    """
    Black borders for the whole table.
    size is in 1/8 pt units (2 => 1/4pt).
    """
    tblPr = tbl._tbl.tblPr
    borders = tblPr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tblPr.append(borders)

    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))      # ✅ 1/4pt
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")    # ✅ BLACK


def _shade_cell(cell, fill_hex: str) -> None:
    """Solid fill for a cell (header blue)."""
    fill_hex = s(fill_hex).replace("#", "") or "FFFFFF"
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcPr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)


def _clear_cell(cell) -> None:
    """Ensure cell starts empty."""
    cell.text = ""
    if cell.paragraphs:
        cell.paragraphs[0].text = ""
        _compact(cell.paragraphs[0])


def _align_cell_center(cell) -> None:
    """
    Center horizontally + vertically for the first paragraph in the cell.
    Used for NO + Compliance columns.
    """
    try:
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    except Exception:
        pass

    if cell.paragraphs:
        p = cell.paragraphs[0]
        _compact(p)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _align_cell_left_top(cell) -> None:
    """Default text layout for body cells."""
    try:
        cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    except Exception:
        pass
    if cell.paragraphs:
        _compact(cell.paragraphs[0])
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.LEFT


def _add_picture_stack_in_cell(
    cell,
    images: List[bytes],
    *,
    width_in: float = 3.10,
) -> None:
    """
    Adds ALL images into the Photos cell, right-aligned.
    Each image is placed in its own paragraph for clean stacking.
    """
    _clear_cell(cell)
    try:
        cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    except Exception:
        pass

    if not images:
        return

    for img_bytes in images:
        clean = _clean_png(img_bytes)
        if not clean:
            continue
        p = cell.add_paragraph("")
        _compact(p)
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.add_run().add_picture(io.BytesIO(clean), width=Inches(width_in))


def _extract_images_for_row(
    rdata: Dict[str, Any],
    photo_bytes: Dict[str, bytes],
) -> List[bytes]:
    """
    STRICT priority (to guarantee annotated marks are in the report):

    1) annotated_photo_bytes_list  -> EXACT marked images (preferred)
    2) photo_bytes_list            -> original bytes aligned to photos
    3) photos urls -> photo_bytes dict (fallback)
    4) single photo url -> photo_bytes dict (backward)

    Returns a list of bytes to be inserted (ALL of them).
    """
    out: List[bytes] = []

    # 1) Annotated versions (exactly what user marked)
    ann_list = rdata.get("annotated_photo_bytes_list")
    if isinstance(ann_list, list):
        for b in ann_list:
            if isinstance(b, (bytes, bytearray)) and b:
                out.append(bytes(b))

    # 2) If annotation list is empty/missing for some photos, fall back to originals.
    orig_list = rdata.get("photo_bytes_list")
    if isinstance(orig_list, list):
        for b in orig_list:
            if isinstance(b, (bytes, bytearray)) and b:
                out.append(bytes(b))

    # 3) Fallback urls list
    photos = rdata.get("photos")
    if isinstance(photos, list):
        for u in photos:
            u = s(u)
            if not u:
                continue
            b = photo_bytes.get(u)
            if isinstance(b, (bytes, bytearray)) and b:
                out.append(bytes(b))

    # 4) Backward compatible single photo
    u1 = s(rdata.get("photo"))
    if u1:
        b = photo_bytes.get(u1)
        if isinstance(b, (bytes, bytearray)) and b:
            out.append(bytes(b))

    # Soft dedup by (len + first bytes) to avoid repeating exact same image twice
    dedup: List[bytes] = []
    seen = set()
    for b in out:
        sig = (len(b), b[:32])
        if sig in seen:
            continue
        seen.add(sig)
        dedup.append(b)

    return dedup


# =================================================
# PAGE — FINDINGS & RECOMMENDATIONS (INSIDE OBSERVATIONS)
# =================================================
def add_findings_recommendations_page(
    doc: Document,
    *,
    component_observations: List[Dict[str, Any]],
    photo_bytes: Dict[str, bytes],
) -> None:
    """
    ✅ Guarantees:
      - Compliance EXACTLY as user entered (reads rdata["Compliance"])
      - NO audio saved in report
      - Annotated photos saved EXACTLY (uses annotated_photo_bytes_list first)
      - All user photos included (not limited)

    Expected structures (from your Step4 merge):
      component_observations = [
        {
          "comp_id": ...,
          "title": ...,
          "observations_valid": [
            {
              "title": ...,
              "major_table": [
                {
                  "finding": "...",
                  "Compliance": "Yes/No/N/A/...",
                  "photos": [url...],
                  "photo_bytes_list": [bytes|None...],
                  "annotated_photo_bytes_list": [bytes|None...],
                }, ...
              ],
              "recommendations": [str...]
            }, ...
          ]
        }, ...
      ]

    photo_bytes = st.session_state["photo_bytes"] (fallback if needed)
    """
    if not component_observations:
        return

    photo_bytes = photo_bytes or {}

    obs_global_idx = 0  # 5.1, 5.2, ... across components

    for comp in component_observations:
        for obs in comp.get("observations_valid", []) or []:
            obs_global_idx += 1
            obs_no = f"5.{obs_global_idx}"

            # ----------------------------
            # 5.x.1 Major findings
            # ----------------------------
            mf_title = doc.add_paragraph(f"{obs_no}.1 Major findings:")
            mf_title.style = "Heading 3"
            if mf_title.runs:
                mf_title.runs[0].font.color.rgb = RGBColor(0, 0, 0)
            _compact(mf_title)

            _one_line_gap(doc)

            rows = obs.get("major_table") or []
            if rows:
                tbl = doc.add_table(rows=1, cols=4)
                tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
                tbl.style = "Table Grid"

                _set_table_fixed_layout(tbl)
                _set_table_black_borders(tbl, size=BORDER_SZ_EIGHTHS)

                # Set exact widths
                for i, w in enumerate([COL_NO, COL_FIND, COL_COMP, COL_PHOTO]):
                    tbl.columns[i].width = Inches(w)
                    for c in tbl.columns[i].cells:
                        c.width = Inches(w)

                # Header row formatting
                header_fill_blue = "2F5597"
                hdr_cells = tbl.rows[0].cells
                hdr_texts = ["NO", "Findings", "Compliance", "Photos"]

                for c, txt in zip(hdr_cells, hdr_texts):
                    _clear_cell(c)
                    _shade_cell(c, header_fill_blue)

                    p = c.paragraphs[0]
                    _compact(p)
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    try:
                        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                    except Exception:
                        pass

                    r = p.add_run(txt)
                    r.bold = True
                    r.font.size = Pt(10)
                    r.font.color.rgb = RGBColor(255, 255, 255)

                # Data rows
                for idx, rdata in enumerate(rows, start=1):
                    if not isinstance(rdata, dict):
                        continue

                    row_cells = tbl.add_row().cells

                    # --- NO
                    row_cells[0].text = str(idx)
                    _align_cell_center(row_cells[0])

                    # --- Findings
                    row_cells[1].text = s(rdata.get("finding"))
                    _align_cell_left_top(row_cells[1])

                    # --- Compliance (EXACT key)
                    # Important: must be "Compliance" (case-sensitive)
                    row_cells[2].text = s(rdata.get("Compliance"))
                    _align_cell_center(row_cells[2])

                    # --- Photos: EXACT annotated photos first
                    images = _extract_images_for_row(rdata, photo_bytes)
                    _add_picture_stack_in_cell(row_cells[3], images, width_in=3.10)

            # ----------------------------
            # 5.x.2 Recommendations
            # ----------------------------
            recs = obs.get("recommendations") or []
            if recs:
                _one_line_gap(doc)

                rt = doc.add_paragraph(f"{obs_no}.2 Recommendations:")
                rt.style = "Heading 3"
                if rt.runs:
                    rt.runs[0].font.color.rgb = RGBColor(0, 0, 0)
                _compact(rt)

                _one_line_gap(doc)

                for txt in recs:
                    t = s(txt)
                    if not t:
                        continue
                    rp = doc.add_paragraph(t, style="List Bullet")
                    _compact(rp)

            _one_line_gap(doc)
