from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

from docx.document import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
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
# Utils
# -------------------------------------------------
def s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _compact(p):
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0


def _one_line_gap(doc: Document) -> None:
    """
    Exactly one blank line (compact) between blocks.
    """
    p = doc.add_paragraph("")
    _compact(p)


def _clean_png(b: bytes) -> Optional[bytes]:
    try:
        img = Image.open(io.BytesIO(b)).convert("RGB")
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _set_table_fixed_layout(tbl) -> None:
    """
    Prevent Word from auto-resizing columns.
    """
    tbl.autofit = False
    tblPr = tbl._tbl.tblPr
    tblLayout = tblPr.find(qn("w:tblLayout"))
    if tblLayout is None:
        tblLayout = OxmlElement("w:tblLayout")
        tblPr.append(tblLayout)
    tblLayout.set(qn("w:type"), "fixed")


def _set_table_black_borders(tbl, *, size: str = "8") -> None:
    """
    Black borders for the whole table.
    size is in 1/8 pt units (8 => 1pt).
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
        el.set(qn("w:sz"), str(size))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")  # ✅ BLACK


def _shade_cell(cell, fill_hex: str) -> None:
    """
    Solid fill for a cell (header blue).
    """
    fill_hex = s(fill_hex).replace("#", "") or "FFFFFF"
    tcPr = cell._tc.get_or_add_tcPr()
    shd = tcPr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tcPr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)


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
    ✅ IMPORTANT CHANGES (per your requirements):
      - NO "5. Findings & Recommendations" heading (not a separate section)
      - For each Observation (assumed numbered as 5.1, 5.2, ...):
          5.1.1 Major findings:
          (table)
          5.1.2 Recommendations:
      - One blank line between each title and its table/content
      - Table borders: BLACK
      - Header row: BLUE fill + WHITE text + BOLD + size 10
    """
    if not component_observations:
        return

    photo_bytes = photo_bytes or {}

    # NOTE: No page break here (because it's part of Observations).
    # If you still want it on a new page, add doc.add_page_break() from the caller side.

    obs_global_idx = 0  # 5.1, 5.2, ... across components

    for comp in component_observations:
        for obs in comp.get("observations_valid", []) or []:
            obs_global_idx += 1
            obs_no = f"5.{obs_global_idx}"  # Observation number like 5.1

            # ----------------------------
            # 5.x.1 Major findings
            # ----------------------------
            mf_title = doc.add_paragraph(f"{obs_no}.1 Major findings:")
            mf_title.style = "Heading 3"
            # Force black (per your request)
            if mf_title.runs:
                mf_title.runs[0].font.color.rgb = RGBColor(0, 0, 0)
            _compact(mf_title)

            # ✅ exactly one line gap before table
            _one_line_gap(doc)

            rows = obs.get("major_table") or []
            if rows:
                tbl = doc.add_table(rows=1, cols=4)
                tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
                tbl.style = "Table Grid"

                _set_table_fixed_layout(tbl)
                _set_table_black_borders(tbl, size="5")  # ✅ black borders

                # Set exact widths
                for i, w in enumerate([COL_NO, COL_FIND, COL_COMP, COL_PHOTO]):
                    tbl.columns[i].width = Inches(w)
                    for c in tbl.columns[i].cells:
                        c.width = Inches(w)

                # Header row formatting
                header_fill_blue = "2F5597"  # ✅ blue header
                hdr_cells = tbl.rows[0].cells
                hdr_texts = ["NO", "Findings", "Compliance", "Photos"]

                for c, txt in zip(hdr_cells, hdr_texts):
                    c.text = txt
                    _shade_cell(c, header_fill_blue)

                    p = c.paragraphs[0]
                    _compact(p)
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

                    if p.runs:
                        r = p.runs[0]
                        r.bold = True
                        r.font.size = Pt(10)  # ✅ size 10
                        r.font.color.rgb = RGBColor(255, 255, 255)  # ✅ white

                # Data rows
                for i, rdata in enumerate(rows, start=1):
                    row_cells = tbl.add_row().cells

                    row_cells[0].text = str(i)
                    row_cells[1].text = s(rdata.get("finding"))
                    row_cells[2].text = s(rdata.get("compliance"))

                    # Photos cell
                    pph = row_cells[3].paragraphs[0]
                    pph.text = ""
                    _compact(pph)
                    pph.alignment = WD_ALIGN_PARAGRAPH.RIGHT

                    u = s(rdata.get("photo"))
                    b = photo_bytes.get(u)
                    if b:
                        clean = _clean_png(b)
                        if clean:
                            pph.add_run().add_picture(
                                io.BytesIO(clean),
                                width=Inches(3.1),
                            )

                    # compact text cells
                    for c in row_cells[:3]:
                        if c.paragraphs:
                            _compact(c.paragraphs[0])

            # ----------------------------
            # 5.x.2 Recommendations
            # ----------------------------
            recs = obs.get("recommendations") or []
            if recs:
                # ✅ one line gap after table (or after Major findings title if no table)
                _one_line_gap(doc)

                rt = doc.add_paragraph(f"{obs_no}.2 Recommendations:")
                rt.style = "Heading 3"
                if rt.runs:
                    rt.runs[0].font.color.rgb = RGBColor(0, 0, 0)
                _compact(rt)

                # ✅ one line gap before bullets
                _one_line_gap(doc)

                for txt in recs:
                    rp = doc.add_paragraph(s(txt), style="List Bullet")
                    _compact(rp)

            # ✅ optional spacer after each observation block (keeps sections readable)
            _one_line_gap(doc)

