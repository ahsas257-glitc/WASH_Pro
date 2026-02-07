from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional

from PIL import Image
from docx.document import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


# =========================
# CONSTANTS (match Step 3)
# =========================
PHOTO_W_IN = 3.17
PHOTO_H_IN = 2.38
PHOTO_ASPECT = PHOTO_W_IN / PHOTO_H_IN  # ~1.3328

# ✅ Equal split like preview
LEFT_W_IN = 3.25
RIGHT_W_IN = 3.25

# spacing between photo blocks inside an observation
PHOTO_GAP_LINES = 1  # clean spacing

# Major findings table widths (must fit page)
MF_COL_NO = 0.38
MF_COL_FIND = 2.88
MF_COL_COMP = 0.91
MF_COL_PHOTO = 3.13
MF_COL_WIDTHS = [MF_COL_NO, MF_COL_FIND, MF_COL_COMP, MF_COL_PHOTO]

# Header styling
MF_HEADER_FILL_HEX = "2F5597"
MF_BORDER_HEX = "000000"


# =========================
# HELPERS
# =========================
def s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _compact(p) -> None:
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0


def _one_line_gap(doc: Document) -> None:
    p = doc.add_paragraph("")
    _compact(p)


def _set_table_fixed_layout(tbl) -> None:
    """Force Word to keep column widths stable."""
    try:
        tbl.allow_autofit = False  # type: ignore[attr-defined]
    except Exception:
        pass

    tbl.autofit = False
    tblPr = tbl._tbl.tblPr
    tblLayout = tblPr.find(qn("w:tblLayout"))
    if tblLayout is None:
        tblLayout = OxmlElement("w:tblLayout")
        tblPr.append(tblLayout)
    tblLayout.set(qn("w:type"), "fixed")


def _apply_2col_widths(tbl, left_w_in: float, right_w_in: float) -> None:
    _set_table_fixed_layout(tbl)

    tbl.columns[0].width = Inches(left_w_in)
    tbl.columns[1].width = Inches(right_w_in)

    for row in tbl.rows:
        row.cells[0].width = Inches(left_w_in)
        row.cells[1].width = Inches(right_w_in)


def _apply_table_col_widths(tbl, widths_in: List[float]) -> None:
    _set_table_fixed_layout(tbl)
    for i, w in enumerate(widths_in):
        tbl.columns[i].width = Inches(float(w))
        for cell in tbl.columns[i].cells:
            cell.width = Inches(float(w))


def _remove_table_borders(tbl) -> None:
    tblPr = tbl._tbl.tblPr
    borders = tblPr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tblPr.append(borders)
    for k in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = borders.find(qn(f"w:{k}"))
        if e is None:
            e = OxmlElement(f"w:{k}")
            borders.append(e)
        e.set(qn("w:val"), "nil")


def _set_table_borders(tbl, *, color_hex: str = MF_BORDER_HEX, size: str = "12") -> None:
    """Black borders (size in eighths of a point). 12 => 1.5pt."""
    color_hex = s(color_hex).replace("#", "") or "000000"
    t = tbl._tbl
    tbl_pr = t.tblPr
    borders = tbl_pr.first_child_found_in("w:tblBorders")
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)

    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            borders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color_hex)


def _shade_cell(cell, fill_hex: str) -> None:
    fill_hex = s(fill_hex).replace("#", "") or "FFFFFF"
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)


def _set_cell_margins(cell, start=80, end=80, top=0, bottom=0) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = tcPr.find(qn("w:tcMar"))
    if tcMar is None:
        tcMar = OxmlElement("w:tcMar")
        tcPr.append(tcMar)

    for name, val in (("start", start), ("end", end), ("top", top), ("bottom", bottom)):
        node = tcMar.find(qn(f"w:{name}"))
        if node is None:
            node = OxmlElement(f"w:{name}")
            tcMar.append(node)
        node.set(qn("w:w"), str(int(val)))
        node.set(qn("w:type"), "dxa")


def _bytes_look_like_html(data: bytes) -> bool:
    head = (data or b"")[:300].lower()
    return b"<!doctype html" in head or b"<html" in head or b"<head" in head


def _crop_to_aspect(img: Image.Image, target_aspect: float) -> Image.Image:
    w, h = img.size
    if w <= 0 or h <= 0:
        return img
    current = w / h
    if abs(current - target_aspect) < 1e-3:
        return img
    if current > target_aspect:
        new_w = int(h * target_aspect)
        left = max(0, (w - new_w) // 2)
        return img.crop((left, 0, left + new_w, h))
    new_h = int(w / target_aspect)
    top = max(0, (h - new_h) // 2)
    return img.crop((0, top, w, top + new_h))


def _to_clean_png_fit_box(b: bytes, *, target_aspect: float) -> Optional[bytes]:
    """Crop to target aspect + export PNG (like Step 3)."""
    if not b or _bytes_look_like_html(b):
        return None
    try:
        img = Image.open(io.BytesIO(b)).convert("RGB")
        img = _crop_to_aspect(img, target_aspect)
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _add_blank_lines_in_cell(cell, n: int) -> None:
    for _ in range(max(0, int(n))):
        p = cell.add_paragraph("")
        _compact(p)


def _extract_obs_no_prefix(obs_title: str) -> str:
    """From: '5.1. Some title' -> '5.1'"""
    t = s(obs_title)
    m = re.match(r"^\s*(\d+\.\d+)\.", t)
    return m.group(1) if m else ""


def _set_run_font(run, *, size_pt: int, bold: bool, color: Optional[RGBColor] = None) -> None:
    try:
        run.font.size = Pt(float(size_pt))
    except Exception:
        pass
    run.bold = bool(bold)
    if color is not None:
        try:
            run.font.color.rgb = color
        except Exception:
            pass


def _write_cell_text(
    cell,
    text: Any,
    *,
    align=WD_ALIGN_PARAGRAPH.LEFT,
    bold: bool = False,
    size_pt: int = 9,
    color: Optional[RGBColor] = None,
) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    _compact(p)
    r = p.add_run(s(text))
    _set_run_font(r, size_pt=size_pt, bold=bold, color=color)


def _add_major_findings_table(
    doc: Document,
    *,
    major_rows: List[Dict[str, Any]],
    photo_bytes: Dict[str, bytes],
) -> None:
    """Table with black borders, blue header, white bold text size 10."""
    tbl = doc.add_table(rows=1, cols=4)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl.style = "Table Grid"
    _set_table_fixed_layout(tbl)
    _set_table_borders(tbl, color_hex=MF_BORDER_HEX, size="12")
    _apply_table_col_widths(tbl, MF_COL_WIDTHS)

    headers = ["NO", "Findings", "Compliance", "Photos"]
    hdr_cells = tbl.rows[0].cells

    for i, txt in enumerate(headers):
        c = hdr_cells[i]
        c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        _shade_cell(c, MF_HEADER_FILL_HEX)
        _set_cell_margins(c, start=90, end=90, top=50, bottom=50)
        _write_cell_text(
            c,
            txt,
            align=WD_ALIGN_PARAGRAPH.CENTER,
            bold=True,
            size_pt=10,
            color=RGBColor(255, 255, 255),
        )

    for idx, rdata in enumerate(major_rows, start=1):
        if not isinstance(rdata, dict):
            continue

        row = tbl.add_row().cells
        for c in row:
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            _set_cell_margins(c, start=90, end=90, top=50, bottom=50)

        _write_cell_text(row[0], str(idx), align=WD_ALIGN_PARAGRAPH.LEFT, bold=False, size_pt=9)
        _write_cell_text(row[1], rdata.get("finding"), align=WD_ALIGN_PARAGRAPH.LEFT, bold=False, size_pt=9)
        _write_cell_text(row[2], rdata.get("compliance"), align=WD_ALIGN_PARAGRAPH.LEFT, bold=False, size_pt=9)

        # Photo cell
        row[3].text = ""
        pph = row[3].paragraphs[0]
        pph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _compact(pph)

        u = s(rdata.get("photo"))
        embedded = rdata.get("photo_bytes")
        if isinstance(embedded, bytearray):
            embedded = bytes(embedded)

        b = embedded if isinstance(embedded, (bytes, bytearray)) and embedded else (photo_bytes.get(u) if u else None)
        clean = _to_clean_png_fit_box(b, target_aspect=PHOTO_ASPECT) if b else None
        if clean:
            pph.add_run().add_picture(io.BytesIO(clean), width=Inches(MF_COL_PHOTO - 0.05))


def _add_photo_block_row(
    doc: Document,
    *,
    left_text: str,
    img_png: Optional[bytes],
) -> None:
    """
    ✅ Like Step 3 preview:
      2-col borderless row
        LEFT  = per-photo text (NOT justified)
        RIGHT = image (aligned right)
    """
    tbl = doc.add_table(rows=1, cols=2)
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    _remove_table_borders(tbl)
    _apply_2col_widths(tbl, LEFT_W_IN, RIGHT_W_IN)

    left, right = tbl.rows[0].cells
    left.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    right.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP

    _set_cell_margins(left, start=80, end=120)
    _set_cell_margins(right, start=120, end=80)

    # LEFT text
    p1 = left.paragraphs[0]
    p1.text = s(left_text)
    p1.alignment = WD_ALIGN_PARAGRAPH.LEFT  # ✅ not justify
    _compact(p1)

    # RIGHT image
    right.paragraphs[0].text = ""
    _compact(right.paragraphs[0])

    if img_png:
        pic_p = right.add_paragraph()
        pic_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        _compact(pic_p)
        pic_p.add_run().add_picture(
            io.BytesIO(img_png),
            width=Inches(PHOTO_W_IN),
            height=Inches(PHOTO_H_IN),
        )


# =========================
# PUBLIC API
# =========================
def add_observations_page(
    doc: Document,
    *,
    component_observations: List[Dict[str, Any]],
    photo_bytes: Dict[str, bytes],
) -> None:
    """
    Expected schema (NEW):
      component_observations = [
        {
          "comp_id": "...",
          "title": "...",
          "observations_valid": [
            {
              "title": "5.1. ...",
              "audio_url": "...",
              "photos": [{"url": "...", "text": "...", "bytes": b"..."}]
            }
          ]
        }
      ]
    """
    if not component_observations:
        return

    photo_bytes = photo_bytes or {}

    # Page break + title
    doc.add_page_break()
    h = doc.add_paragraph("5. Observations")
    h.style = "Heading 1"
    _compact(h)

    for comp in component_observations:
        if not isinstance(comp, dict):
            continue

        comp_hdr = f"{s(comp.get('comp_id'))} — {s(comp.get('title'))}".strip(" —")
        ch = doc.add_paragraph(comp_hdr)
        ch.style = "Heading 2"
        _compact(ch)

        for obs in (comp.get("observations_valid") or []):
            if not isinstance(obs, dict):
                continue

            # Observation title
            obs_title = s(obs.get("title"))
            ot = doc.add_paragraph(obs_title)
            ot.style = "Heading 2"
            _compact(ot)
            if ot.runs:
                try:
                    ot.runs[0].font.size = Pt(16)
                except Exception:
                    pass

            # Optional audio (just show URL line)
            audio_url = s(obs.get("audio_url"))
            if audio_url:
                ap = doc.add_paragraph(f"Audio: {audio_url}")
                _compact(ap)
                if ap.runs:
                    try:
                        ap.runs[0].italic = True
                        ap.runs[0].font.size = Pt(9)
                    except Exception:
                        pass

            photos = obs.get("photos") or []
            if not isinstance(photos, list):
                photos = []

            if not photos:
                # if no photos, just leave a small gap
                _one_line_gap(doc)
            else:
                # For each photo: left=text, right=image (like preview)
                for i, ph in enumerate(photos):
                    if not isinstance(ph, dict):
                        continue

                    url = s(ph.get("url"))
                    txt = s(ph.get("text"))
                    embedded = ph.get("bytes")
                    if isinstance(embedded, bytearray):
                        embedded = bytes(embedded)

                    b = embedded if isinstance(embedded, (bytes, bytearray)) and embedded else (photo_bytes.get(url) if url else None)
                    clean = _to_clean_png_fit_box(b, target_aspect=PHOTO_ASPECT) if b else None

                    if i > 0:
                        _one_line_gap(doc)  # spacing between photo blocks

                    # Graceful messages (but still stable layout)
                    if not url and not clean:
                        _add_photo_block_row(doc, left_text=txt or "Photo missing: empty url", img_png=None)
                        continue
                    if not b:
                        _add_photo_block_row(doc, left_text=txt or f"Photo missing (not cached): {url}", img_png=None)
                        continue
                    if not clean:
                        _add_photo_block_row(doc, left_text=txt or f"Photo unreadable: {url}", img_png=None)
                        continue

                    _add_photo_block_row(doc, left_text=txt, img_png=clean)

                _one_line_gap(doc)

            # =====================================================
            # Major findings + Recommendations (unchanged logic)
            # =====================================================
            base_no = _extract_obs_no_prefix(obs_title)  # "5.1"
            if base_no:
                major_title = f"{base_no}.1 Major findings:"
                reco_title = f"{base_no}.2 Recommendations:"
            else:
                major_title = "Major findings:"
                reco_title = "Recommendations:"

            major_rows = obs.get("major_table") or []
            if isinstance(major_rows, list) and len(major_rows) > 0:
                mh = doc.add_paragraph(major_title)
                mh.style = "Heading 3"
                _compact(mh)
                if mh.runs:
                    mh.runs[0].font.color.rgb = RGBColor(0, 0, 0)

                _one_line_gap(doc)

                _add_major_findings_table(
                    doc,
                    major_rows=major_rows,
                    photo_bytes=photo_bytes,
                )

                _one_line_gap(doc)

            recs = obs.get("recommendations") or []
            if isinstance(recs, list) and any(s(x) for x in recs):
                rh = doc.add_paragraph(reco_title)
                rh.style = "Heading 3"
                _compact(rh)
                if rh.runs:
                    rh.runs[0].font.color.rgb = RGBColor(0, 0, 0)

                _one_line_gap(doc)

                for txt in recs:
                    t = s(txt)
                    if not t:
                        continue
                    rp = doc.add_paragraph(t, style="List Bullet")
                    _compact(rp)

                _one_line_gap(doc)
