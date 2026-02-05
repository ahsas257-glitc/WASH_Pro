# src/report_sections/summary_of_findings.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union

from docx.document import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT, WD_ROW_HEIGHT_RULE
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, RGBColor, Pt
from docx.text.paragraph import Paragraph


# ============================================================
# Inline helpers (replacing src.report_sections._word_common)
# ============================================================
def s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def tight_paragraph(
    p: Paragraph,
    *,
    align=WD_ALIGN_PARAGRAPH.LEFT,
    before_pt: Union[int, float] = 0,
    after_pt: Union[int, float] = 0,
    line_spacing: float = 1.0,
) -> None:
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(float(before_pt))
    pf.space_after = Pt(float(after_pt))
    pf.line_spacing = float(line_spacing)


def set_run(
    run,
    font: str,
    size: Union[int, float],
    bold: bool = False,
    color: Optional[RGBColor] = None,
) -> None:
    try:
        run.font.name = font
    except Exception:
        pass
    try:
        run._element.rPr.rFonts.set(qn("w:eastAsia"), font)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        run.font.size = Pt(float(size))
    except Exception:
        pass
    run.bold = bool(bold)
    if color is not None:
        try:
            run.font.color.rgb = color
        except Exception:
            pass


# -------------------------
# Heading 1 with orange underline (TOC-friendly)
# -------------------------
def _set_paragraph_bottom_border(
    paragraph: Paragraph,
    *,
    color_hex: str,
    size_eighths: int = 12,  # 12 => 1.5pt
    space: int = 2,
) -> None:
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = pPr.find(qn("w:pBdr"))
    if pBdr is None:
        pBdr = OxmlElement("w:pBdr")
        pPr.append(pBdr)

    bottom = pBdr.find(qn("w:bottom"))
    if bottom is None:
        bottom = OxmlElement("w:bottom")
        pBdr.append(bottom)

    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(int(size_eighths)))
    bottom.set(qn("w:space"), str(int(space)))
    bottom.set(qn("w:color"), s(color_hex).replace("#", ""))


def add_section_title_h1(
    doc: Document,
    text: str,
    *,
    font: str = "Cambria",
    size: int = 16,
    color: RGBColor = RGBColor(0, 112, 192),
    orange_hex: str = "ED7D31",
    after_pt: Union[int, float] = 6,
) -> Paragraph:
    """
    ✅ Proper Heading 1 (TOC-friendly) + orange underline on SAME paragraph
    """
    p = doc.add_paragraph()
    try:
        p.style = "Heading 1"
    except Exception:
        pass

    r = p.add_run(s(text))
    set_run(r, font, size, bold=True, color=color)
    tight_paragraph(p, align=WD_ALIGN_PARAGRAPH.LEFT, before_pt=0, after_pt=float(after_pt), line_spacing=1.0)
    _set_paragraph_bottom_border(p, color_hex=orange_hex, size_eighths=12, space=2)
    return p


# -------------------------
# Table/layout helpers
# -------------------------
def _emu_to_twips(emu: int) -> int:
    # 1 inch = 914400 EMU = 1440 twips => twips = emu / 635
    return int(round(int(emu) / 635.0))


def section_usable_width_emu(section) -> int:
    """
    Returns usable page width for a section in EMU: page_width - margins.
    """
    try:
        return int(section.page_width.emu - section.left_margin.emu - section.right_margin.emu)
    except Exception:
        # fallback: best effort
        return int(section.page_width - section.left_margin - section.right_margin)


def set_table_fixed_layout(table) -> None:
    tbl = table._tbl
    tblPr = tbl.tblPr
    tblLayout = tblPr.find(qn("w:tblLayout"))
    if tblLayout is None:
        tblLayout = OxmlElement("w:tblLayout")
        tblPr.append(tblLayout)
    tblLayout.set(qn("w:type"), "fixed")


def set_table_width_from_section(table, doc: Document, *, section_index: int = 0) -> None:
    """
    Set table width to the usable width of a given section.
    """
    section = doc.sections[section_index]
    usable_emu = section_usable_width_emu(section)

    tbl = table._tbl
    tblPr = tbl.tblPr

    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:type"), "dxa")
    tblW.set(qn("w:w"), str(_emu_to_twips(usable_emu)))

    # Remove indent for consistent left alignment
    tblInd = tblPr.find(qn("w:tblInd"))
    if tblInd is None:
        tblInd = OxmlElement("w:tblInd")
        tblPr.append(tblInd)
    tblInd.set(qn("w:type"), "dxa")
    tblInd.set(qn("w:w"), "0")


def set_table_borders(table, *, color_hex: str = "000000", size: str = "8") -> None:
    color_hex = s(color_hex).replace("#", "") or "000000"
    tbl = table._tbl
    tbl_pr = tbl.tblPr
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


def set_cell_borders(cell, *, size: int = 8, color_hex: str = "000000") -> None:
    """
    Apply cell borders (all sides).
    """
    color_hex = s(color_hex).replace("#", "") or "000000"
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = tcPr.find(qn("w:tcBorders"))
    if tcBorders is None:
        tcBorders = OxmlElement("w:tcBorders")
        tcPr.append(tcBorders)

    for edge in ("top", "left", "bottom", "right"):
        el = tcBorders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            tcBorders.append(el)
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), str(int(size)))
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), color_hex)


def shade_cell(cell, fill_hex: str) -> None:
    fill_hex = s(fill_hex).replace("#", "") or "FFFFFF"
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)


def set_cell_margins(
    cell,
    *,
    top_dxa: int = 80,
    bottom_dxa: int = 80,
    left_dxa: int = 120,
    right_dxa: int = 120,
) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = tcPr.find(qn("w:tcMar"))
    if tcMar is None:
        tcMar = OxmlElement("w:tcMar")
        tcPr.append(tcMar)

    def _set(side: str, val: int) -> None:
        el = tcMar.find(qn(f"w:{side}"))
        if el is None:
            el = OxmlElement(f"w:{side}")
            tcMar.append(el)
        el.set(qn("w:w"), str(int(val)))
        el.set(qn("w:type"), "dxa")

    _set("top", top_dxa)
    _set("bottom", bottom_dxa)
    _set("start", left_dxa)
    _set("end", right_dxa)


def set_row_cant_split(row, *, cant_split: bool = True) -> None:
    tr = row._tr
    trPr = tr.get_or_add_trPr()
    existing = trPr.find(qn("w:cantSplit"))
    if cant_split:
        if existing is None:
            trPr.append(OxmlElement("w:cantSplit"))
    else:
        if existing is not None:
            trPr.remove(existing)


def set_row_height_exact(row, height_in: float) -> None:
    row.height = Inches(float(height_in))
    row.height_rule = WD_ROW_HEIGHT_RULE.EXACTLY


def set_row_height_at_least(row, height_in: float) -> None:
    row.height = Inches(float(height_in))
    row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST


# ============================================================
# Section-6 shared helpers (inline)
# ============================================================
def normalize_sentence(v: Any) -> str:
    """
    Clean sentence text for Word:
    - stringify/trim
    - collapse internal whitespace
    - keep em-dash line if empty
    - ensure final punctuation (.)
    """
    sv = s(v)
    if not sv:
        return ""
    sv = " ".join(sv.split())
    sv = sv.strip()
    # don't force punctuation for bullets like "—"
    if sv and sv not in ("—", "-"):
        if sv[-1] not in ".!?":
            sv += "."
    # Capitalize first letter (gentle)
    if sv and sv[0].isalpha():
        sv = sv[0].upper() + sv[1:]
    return sv


def _checkbox(checked: bool) -> str:
    return "☒" if checked else "☐"


def severity_checkbox_line(chosen: Any) -> str:
    """
    Returns: ☒ High  ☐ Medium  ☐ Low (based on chosen)
    """
    sv = s(chosen).lower()
    high = "high" in sv
    med = "medium" in sv
    low = "low" in sv
    return f"{_checkbox(high)} High   {_checkbox(med)} Medium   {_checkbox(low)} Low"


def extract_findings_and_recos_from_section5(component_observations: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Robust extraction for Section 6 summary from Section 5 structures.
    Accepts multiple possible shapes and returns a flat list of:
      [{"finding": "...", "recommendation": "..."}, ...]
    """
    out: List[Dict[str, str]] = []

    def add_one(f: Any, r: Any) -> None:
        f_s = s(f)
        r_s = s(r)
        if f_s or r_s:
            out.append({"finding": f_s, "recommendation": r_s})

    for item in component_observations or []:
        if not isinstance(item, dict):
            continue

        # Case A: direct keys
        if any(k in item for k in ("finding", "recommendation", "corrective_action")):
            add_one(item.get("finding"), item.get("recommendation", item.get("corrective_action")))
            continue

        # Case B: common alternative keys
        if any(k in item for k in ("observation", "issue", "recommendations", "reco")):
            add_one(
                item.get("observation", item.get("issue")),
                item.get("recommendation", item.get("recommendations", item.get("reco"))),
            )
            continue

        # Case C: nested lists (e.g., findings list)
        for list_key in ("findings", "observations", "issues"):
            lst = item.get(list_key)
            if isinstance(lst, list):
                for sub in lst:
                    if isinstance(sub, dict):
                        add_one(
                            sub.get("finding", sub.get("observation", sub.get("issue"))),
                            sub.get("recommendation", sub.get("corrective_action", sub.get("reco"))),
                        )
                    else:
                        # if it's just strings
                        add_one(sub, "")
                break

        # Case D: if the item itself is a component with a list of "recommendations"
        recos = item.get("recommendations")
        if isinstance(recos, list) and not out:
            for r in recos:
                add_one(item.get("component", ""), r)

    # remove empties
    cleaned: List[Dict[str, str]] = []
    for d in out:
        f = s(d.get("finding"))
        r = s(d.get("recommendation"))
        if f:  # keep only if finding exists (section 6 uses finding as primary)
            cleaned.append({"finding": f, "recommendation": r})
    return cleaned


def present_severities_from_mapping(
    extracted: List[Dict[str, Any]],
    severity_by_no: Dict[int, str],
    severity_by_finding: Dict[str, str],
) -> List[str]:
    """
    Detect which severities are present based on mappings and extracted list.
    Returns in canonical order: High, Medium, Low (only those present).
    """
    found = set()

    # by number mapping
    for i in range(1, len(extracted) + 1):
        sv = s(severity_by_no.get(i))
        if sv:
            l = sv.lower()
            if "high" in l:
                found.add("High")
            elif "medium" in l:
                found.add("Medium")
            elif "low" in l:
                found.add("Low")

    # by finding mapping
    for item in extracted:
        f = normalize_sentence(item.get("finding", "")).lower()
        for k, v in (severity_by_finding or {}).items():
            if normalize_sentence(k).lower() == f:
                lv = s(v).lower()
                if "high" in lv:
                    found.add("High")
                elif "medium" in lv:
                    found.add("Medium")
                elif "low" in lv:
                    found.add("Low")
                break

    order = ["High", "Medium", "Low"]
    return [x for x in order if x in found]


# ============================================================
# Style (keep section-specific only)
# ============================================================
TITLE_TEXT = "6.        Summary of the findings:"
TITLE_FONT = "Cambria"
TITLE_SIZE = 16
TITLE_BLUE = RGBColor(0, 112, 192)
ORANGE_HEX = "ED7D31"

DARK_BLUE_HEX = "1F4E79"
BORDER_HEX = "000000"
HEADER_TEXT_COLOR = RGBColor(255, 255, 255)

FONT_BODY = "Times New Roman"
FONT_SIZE_BODY = 10
FONT_SIZE_HEADER = 10


def add_summary_of_findings_section6(
    doc: Document,
    *,
    component_observations: List[Dict[str, Any]],
    severity_by_no: Optional[Dict[int, str]] = None,
    severity_by_finding: Optional[Dict[str, str]] = None,
    add_legend: bool = True,
) -> None:
    """
    Section 6:
      - Summary of the findings table
      - Legend table (optional)
    """
    severity_by_no = severity_by_no or {}
    severity_by_finding = severity_by_finding or {}

    doc.add_page_break()

    # ✅ Proper Heading 1 + orange underline on SAME paragraph (no extra blank title line)
    add_section_title_h1(
        doc,
        TITLE_TEXT,
        font=TITLE_FONT,
        size=TITLE_SIZE,
        color=TITLE_BLUE,
        orange_hex=ORANGE_HEX,
        after_pt=6,
    )
    doc.add_paragraph("")

    extracted = extract_findings_and_recos_from_section5(component_observations or [])
    if not extracted:
        p = doc.add_paragraph()
        tight_paragraph(p, align=WD_ALIGN_PARAGRAPH.LEFT, before_pt=0, after_pt=0, line_spacing=1)
        r = p.add_run("No major findings were captured in Section 5 to summarize.")
        set_run(r, "Times New Roman", 11, bold=False)
        return

    # usable width (for “remaining column width” calculation)
    usable_emu = section_usable_width_emu(doc.sections[0])
    usable_in = usable_emu / 914400.0  # EMU -> inch

    # ---- Main table
    table = doc.add_table(rows=1, cols=4)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.style = "Table Grid"

    set_table_fixed_layout(table)
    set_table_width_from_section(table, doc, section_index=0)
    set_table_borders(table, color_hex=BORDER_HEX, size="8")

    # Column widths (inches; stable)
    w_no = 0.45
    w_find = 4.20
    w_sev = 0.80
    w_rec = max(0.90, usable_in - (w_no + w_find + w_sev))

    widths = [Inches(w_no), Inches(w_find), Inches(w_sev), Inches(w_rec)]
    headers = ["No.", "Finding", "Severity", "Recommendation\n/ Corrective\nAction"]

    # Header row
    header_row = table.rows[0]
    set_row_cant_split(header_row, cant_split=True)
    set_row_height_exact(header_row, 0.22)

    for i, cell in enumerate(header_row.cells):
        cell.width = widths[i]
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        cell.text = ""

        shade_cell(cell, DARK_BLUE_HEX)
        set_cell_borders(cell, size=10, color_hex=BORDER_HEX)
        set_cell_margins(cell, top_dxa=80, bottom_dxa=80, left_dxa=120, right_dxa=120)

        p = cell.paragraphs[0]
        tight_paragraph(p, align=WD_ALIGN_PARAGRAPH.CENTER, before_pt=0, after_pt=0, line_spacing=1)
        rr = p.add_run(headers[i])
        set_run(rr, FONT_BODY, FONT_SIZE_HEADER, True, HEADER_TEXT_COLOR)

    # Body rows
    for idx, item in enumerate(extracted, start=1):
        finding = normalize_sentence(item.get("finding", ""))
        reco = normalize_sentence(item.get("recommendation", "")) or "—"

        row = table.add_row()

        # ✅ IMPORTANT: allow split to avoid huge whitespace when finding text is long
        set_row_cant_split(row, cant_split=False)

        set_row_height_at_least(row, 0.36)

        cells = row.cells
        for i, c in enumerate(cells):
            c.width = widths[i]
            c.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            c.text = ""
            set_cell_borders(c, size=8, color_hex=BORDER_HEX)
            set_cell_margins(c, top_dxa=80, bottom_dxa=80, left_dxa=120, right_dxa=120)

        # No
        p0 = cells[0].paragraphs[0]
        tight_paragraph(p0, align=WD_ALIGN_PARAGRAPH.LEFT, before_pt=0, after_pt=0, line_spacing=1)
        set_run(p0.add_run(str(idx)), FONT_BODY, FONT_SIZE_BODY, False)

        # Finding
        p1 = cells[1].paragraphs[0]
        tight_paragraph(p1, align=WD_ALIGN_PARAGRAPH.LEFT, before_pt=0, after_pt=0, line_spacing=1)
        set_run(p1.add_run(finding), FONT_BODY, FONT_SIZE_BODY, False)

        # Severity (checkbox line)
        chosen = ""
        if idx in severity_by_no:
            chosen = s(severity_by_no.get(idx))
        else:
            # match by normalized finding
            f_norm = finding.lower()
            for k, v in severity_by_finding.items():
                if normalize_sentence(k).lower() == f_norm:
                    chosen = s(v)
                    break

        p2 = cells[2].paragraphs[0]
        tight_paragraph(p2, align=WD_ALIGN_PARAGRAPH.LEFT, before_pt=0, after_pt=0, line_spacing=1)
        set_run(p2.add_run(severity_checkbox_line(chosen)), FONT_BODY, 9, False)

        # Recommendation
        p3 = cells[3].paragraphs[0]
        tight_paragraph(p3, align=WD_ALIGN_PARAGRAPH.LEFT, before_pt=0, after_pt=0, line_spacing=1)
        set_run(p3.add_run(reco), FONT_BODY, FONT_SIZE_BODY, False)

    doc.add_paragraph("")

    # ---- Legend
    if not add_legend:
        return

    p_leg = doc.add_paragraph()
    tight_paragraph(p_leg, align=WD_ALIGN_PARAGRAPH.LEFT, before_pt=0, after_pt=0, line_spacing=1)
    set_run(p_leg.add_run("Legend:"), "Times New Roman", 11, True)
    doc.add_paragraph("")

    legend_definitions = {
        "High": "Critical issue affecting functionality, safety, or compliance; requires immediate action.",
        "Medium": "Moderate issue affecting efficiency or performance; corrective action required.",
        "Low": "Minor issue with limited impact; corrective action recommended.",
    }

    present = present_severities_from_mapping(extracted, severity_by_no, severity_by_finding)
    if not present:
        present = ["High", "Medium", "Low"]

    legend = doc.add_table(rows=1, cols=2)
    legend.autofit = False
    legend.alignment = WD_TABLE_ALIGNMENT.LEFT
    legend.style = "Table Grid"

    set_table_fixed_layout(legend)
    set_table_width_from_section(legend, doc, section_index=0)
    set_table_borders(legend, color_hex=BORDER_HEX, size="8")

    # Legend header
    r0 = legend.rows[0]
    set_row_cant_split(r0, cant_split=True)
    set_row_height_exact(r0, 0.22)

    h0, h1c = r0.cells
    for c, txt in ((h0, "Severity"), (h1c, "Definition")):
        c.text = ""
        c.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        shade_cell(c, DARK_BLUE_HEX)
        set_cell_borders(c, size=10, color_hex=BORDER_HEX)
        set_cell_margins(c, top_dxa=80, bottom_dxa=80, left_dxa=120, right_dxa=120)

        pp = c.paragraphs[0]
        tight_paragraph(pp, align=WD_ALIGN_PARAGRAPH.CENTER, before_pt=0, after_pt=0, line_spacing=1)
        set_run(pp.add_run(txt), FONT_BODY, 10, True, HEADER_TEXT_COLOR)

    # Legend rows
    for sev in present:
        rr = legend.add_row()

        # ✅ allow split (legend definitions can wrap)
        set_row_cant_split(rr, cant_split=False)

        set_row_height_at_least(rr, 0.25)

        c0, c1 = rr.cells
        for c in (c0, c1):
            c.text = ""
            c.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            set_cell_borders(c, size=8, color_hex=BORDER_HEX)
            set_cell_margins(c, top_dxa=80, bottom_dxa=80, left_dxa=120, right_dxa=120)

        p0 = c0.paragraphs[0]
        tight_paragraph(p0, align=WD_ALIGN_PARAGRAPH.LEFT, before_pt=0, after_pt=0, line_spacing=1)
        set_run(p0.add_run(sev), FONT_BODY, 10, False)

        p1 = c1.paragraphs[0]
        tight_paragraph(p1, align=WD_ALIGN_PARAGRAPH.LEFT, before_pt=0, after_pt=0, line_spacing=1)
        set_run(p1.add_run(legend_definitions.get(sev, "")), FONT_BODY, 10, False)
