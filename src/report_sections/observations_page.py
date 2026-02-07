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
# CONSTANTS
# =========================
PHOTO_W_IN = 3.17
PHOTO_H_IN = 2.38

# 2-column layout (equal split)
TEXT_COL_W_IN = 3.64
PHOTO_COL_W_IN = 3.64

# spacing between photos inside right column
PHOTO_GAP_LINES = 2  # exactly "two lines"

# Major findings table widths (scaled to fit usable width ~7.29")
# Original sample sum was ~7.92", so we scale down to avoid Word squeezing.
MF_COL_NO = 0.38
MF_COL_FIND = 2.88
MF_COL_COMP = 0.91
MF_COL_PHOTO = 3.13
MF_COL_WIDTHS = [MF_COL_NO, MF_COL_FIND, MF_COL_COMP, MF_COL_PHOTO]

# Header styling
MF_HEADER_FILL_HEX = "2F5597"  # blue (Excel-like)
MF_BORDER_HEX = "000000"       # black border


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
    # exactly one blank line
    p = doc.add_paragraph("")
    _compact(p)


def _set_table_fixed_layout(tbl) -> None:
    """
    Force Word to keep column widths stable (prevents auto-resize).
    """
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
    """
    Black borders (size in eighths of a point). 12 => 1.5pt.
    """
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


def _clean_png(b: bytes) -> Optional[bytes]:
    if not b or _bytes_look_like_html(b):
        return None
    try:
        img = Image.open(io.BytesIO(b)).convert("RGB")
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _add_blank_lines_in_cell(cell, n: int) -> None:
    for _ in range(max(0, int(n))):
        p = cell.add_paragraph("")
        _compact(p)


def _add_note_photo_row(
    *,
    parent_cell,
    note: str,
    img_png: bytes,
) -> None:
    """
    Inside RIGHT column: 1x2 borderless table:
      LEFT  = note
      RIGHT = photo
    """
    t = parent_cell.add_table(rows=1, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    _remove_table_borders(t)
    _set_table_fixed_layout(t)

    note_w = 1.55
    photo_w = max(1.0, PHOTO_COL_W_IN - note_w)

    t.columns[0].width = Inches(note_w)
    t.columns[1].width = Inches(photo_w)
    t.rows[0].cells[0].width = Inches(note_w)
    t.rows[0].cells[1].width = Inches(photo_w)

    c_note, c_photo = t.rows[0].cells
    c_note.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    c_photo.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP

    _set_cell_margins(c_note, start=60, end=100)
    _set_cell_margins(c_photo, start=100, end=60)

    # note
    p_note = c_note.paragraphs[0]
    p_note.text = s(note)
    p_note.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    _compact(p_note)
    if p_note.runs:
        try:
            p_note.runs[0].italic = True
        except Exception:
            pass

    # photo
    p_photo = c_photo.paragraphs[0]
    p_photo.text = ""
    p_photo.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _compact(p_photo)
    p_photo.add_run().add_picture(
        io.BytesIO(img_png),
        width=Inches(PHOTO_W_IN),
        height=Inches(PHOTO_H_IN),
    )


def _extract_obs_no_prefix(obs_title: str) -> str:
    """
    From: "5.1. Some title" -> "5.1"
    """
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
    """
    Table with black borders, blue header, white bold text size 10.
    """
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

    # Body rows
    for idx, rdata in enumerate(major_rows, start=1):
        if not isinstance(rdata, dict):
            continue

        row = tbl.add_row().cells
        for c in row:
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            _set_cell_margins(c, start=90, end=90, top=50, bottom=50)

        _write_cell_text(row[0], str(idx), align=WD_ALIGN_PARAGRAPH.LEFT, bold=False, size_pt=9)
        _write_cell_text(row[1], rdata.get("finding"), align=WD_ALIGN_PARAGRAPH.JUSTIFY, bold=False, size_pt=9)
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

        b = embedded if isinstance(embedded, (bytes, bytearray)) and embedded else photo_bytes.get(u)
        clean = _clean_png(b) if b else None
        if clean:
            pph.add_run().add_picture(io.BytesIO(clean), width=Inches(MF_COL_PHOTO - 0.05))


# =========================
# PUBLIC API
# =========================
def add_observations_page(
    doc: Document,
    *,
    component_observations: List[Dict[str, Any]],
    photo_bytes: Dict[str, bytes],
) -> None:
    if not component_observations:
        return

    photo_bytes = photo_bytes or {}

    # ==========================
    # PAGE TITLE
    # ==========================
    doc.add_page_break()
    h = doc.add_paragraph("5. Observations")
    h.style = "Heading 1"
    _compact(h)

    for comp in component_observations:
        ch = doc.add_paragraph(f"{s(comp.get('comp_id'))} — {s(comp.get('title'))}".strip(" —"))
        ch.style = "Heading 2"
        _compact(ch)

        for obs in comp.get("observations_valid", []) or []:
            # -----------------------------------------
            # Observation title (Heading 2, size 16)
            # -----------------------------------------
            obs_title = s(obs.get("title"))
            ot = doc.add_paragraph(obs_title)
            ot.style = "Heading 2"
            _compact(ot)
            if ot.runs:
                try:
                    ot.runs[0].font.size = Pt(16)
                except Exception:
                    pass

            # -----------------------------------------
            # ✅ Main 2-column fixed layout:
            # LEFT  = text
            # RIGHT = photos
            # -----------------------------------------
            tbl = doc.add_table(rows=1, cols=2)
            tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
            _remove_table_borders(tbl)
            _apply_2col_widths(tbl, TEXT_COL_W_IN, PHOTO_COL_W_IN)

            left, right = tbl.rows[0].cells
            left.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
            right.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP

            _set_cell_margins(left, start=80, end=120)
            _set_cell_margins(right, start=120, end=80)

            # LEFT text
            ptxt = left.paragraphs[0]
            ptxt.text = s(obs.get("text"))
            ptxt.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            _compact(ptxt)

            # RIGHT photos
            right.paragraphs[0].text = ""
            _compact(right.paragraphs[0])

            photos = obs.get("photos") or []
            if not isinstance(photos, list):
                photos = []

            any_added = False
            for i, ph in enumerate(photos):
                if not isinstance(ph, dict):
                    continue

                url = s(ph.get("url"))
                note = s(ph.get("note"))

                embedded = ph.get("bytes")
                if isinstance(embedded, bytearray):
                    embedded = bytes(embedded)

                b = embedded if isinstance(embedded, (bytes, bytearray)) and embedded else photo_bytes.get(url)
                clean = _clean_png(b) if b else None

                # between photos: exactly two blank lines
                if i > 0:
                    _add_blank_lines_in_cell(right, PHOTO_GAP_LINES)

                if not url:
                    p = right.add_paragraph("Photo missing: empty url")
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    _compact(p)
                    continue

                if not b:
                    p = right.add_paragraph(f"Photo missing (not cached): {url}")
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    _compact(p)
                    continue

                if not clean:
                    p = right.add_paragraph(f"Photo unreadable: {url}")
                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                    _compact(p)
                    continue

                _add_note_photo_row(parent_cell=right, note=note, img_png=clean)
                any_added = True

            if not any_added and photos:
                p = right.add_paragraph("Photos were selected but none could be inserted.")
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                _compact(p)

            # spacer after each observation block
            sp = doc.add_paragraph("")
            _compact(sp)

            # =====================================================
            # ✅ Major findings + Recommendations (WITHIN observations)
            # =====================================================
            base_no = _extract_obs_no_prefix(obs_title)  # "5.1"
            if base_no:
                major_title = f"{base_no}.1 Major findings:"
                reco_title = f"{base_no}.2 Recommendations:"
            else:
                major_title = "Major findings:"
                reco_title = "Recommendations:"

            # ---- 5.1.1 Major findings:
            major_rows = obs.get("major_table") or []
            if isinstance(major_rows, list) and len(major_rows) > 0:
                mh = doc.add_paragraph(major_title)
                mh.style = "Heading 3"
                _compact(mh)
                if mh.runs:
                    mh.runs[0].font.color.rgb = RGBColor(0, 0, 0)

                # exactly one line gap between title and table
                _one_line_gap(doc)

                _add_major_findings_table(
                    doc,
                    major_rows=major_rows,
                    photo_bytes=photo_bytes,
                )

                # spacing after table (one line feels clean)
                _one_line_gap(doc)

            # ---- 5.1.2 Recommendations:
            recs = obs.get("recommendations") or []
            if isinstance(recs, list) and any(s(x) for x in recs):
                rh = doc.add_paragraph(reco_title)
                rh.style = "Heading 3"
                _compact(rh)
                if rh.runs:
                    rh.runs[0].font.color.rgb = RGBColor(0, 0, 0)

                # exactly one line gap after title
                _one_line_gap(doc)

                for txt in recs:
                    t = s(txt)
                    if not t:
                        continue
                    rp = doc.add_paragraph(t, style="List Bullet")
                    _compact(rp)

                _one_line_gap(doc)
