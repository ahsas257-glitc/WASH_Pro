# src/report_sections/general_project_information.py
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Optional, List, Union, Tuple

from docx.document import Document
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, RGBColor, Mm, Pt
from docx.text.paragraph import Paragraph


# ============================================================
# Inline helpers (replacing src.report_sections._word_common)
# ============================================================
def s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _is_nonempty(v: Any) -> bool:
    sv = s(v)
    return sv not in ("", " ")


def parse_bool_like(v: Any) -> Optional[bool]:
    """
    Returns True/False/None for common bool-like inputs.
    Handles: bool, 0/1, yes/no, checked/unchecked, ✅/❌, etc.
    """
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        iv = int(v)
        if iv == 1:
            return True
        if iv == 0:
            return False

    sv = s(v).lower()
    if sv in {"yes", "y", "true", "1", "checked", "✔", "✅"}:
        return True
    if sv in {"no", "n", "false", "0", "unchecked", "✘", "❌"}:
        return False
    return None


def _truthy_doc(v: Any) -> bool:
    """
    For document fields: treat True/1/yes as available,
    also treat any non-empty string (file name/url) as available.
    """
    b = parse_bool_like(v)
    if b is True:
        return True
    if b is False:
        return False
    return _is_nonempty(v)


def tight_paragraph(
    p: Paragraph,
    *,
    align=WD_ALIGN_PARAGRAPH.LEFT,
    before_pt: float = 0,
    after_pt: float = 0,
    line_spacing: float = 1.0,
) -> None:
    p.alignment = align
    pf = p.paragraph_format
    pf.space_before = Pt(float(before_pt))
    pf.space_after = Pt(float(after_pt))
    pf.line_spacing = float(line_spacing)


def set_run(run, font: str, size: Union[int, float], bold: bool = False, color: Optional[RGBColor] = None) -> None:
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
# Standard H1 title (TOC + orange line)
# -------------------------
def _set_paragraph_bottom_border(
    paragraph: Paragraph,
    *,
    color_hex: str,
    size_eighths: int = 12,
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
    after_pt: float = 6,
) -> Paragraph:
    """
    ✅ Heading 1 (TOC-friendly) + size 16 + blue text + orange underline line.
    """
    p = doc.add_paragraph()
    try:
        p.style = "Heading 1"
    except Exception:
        pass

    run = p.add_run(s(text))
    set_run(run, font, size, bold=True, color=color)
    tight_paragraph(p, align=WD_ALIGN_PARAGRAPH.LEFT, before_pt=0, after_pt=float(after_pt), line_spacing=1.0)

    _set_paragraph_bottom_border(p, color_hex=orange_hex, size_eighths=12, space=2)
    return p


# -------------------------
# Table/layout helpers
# -------------------------
def _emu_to_twips(emu: int) -> int:
    # 1 inch = 914400 EMU = 1440 twips => twips = emu / 635
    return int(round(int(emu) / 635.0))


def set_table_fixed_layout(table) -> None:
    tbl = table._tbl
    tblPr = tbl.tblPr
    tblLayout = tblPr.find(qn("w:tblLayout"))
    if tblLayout is None:
        tblLayout = OxmlElement("w:tblLayout")
        tblPr.append(tblLayout)
    tblLayout.set(qn("w:type"), "fixed")


def set_table_width_exact(table, width) -> None:
    """
    Set exact table width (width is a docx.shared.Length e.g. Inches()).
    """
    width_emu = int(width.emu)
    tbl = table._tbl
    tblPr = tbl.tblPr

    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:type"), "dxa")
    tblW.set(qn("w:w"), str(_emu_to_twips(width_emu)))

    # Remove indent
    tblInd = tblPr.find(qn("w:tblInd"))
    if tblInd is None:
        tblInd = OxmlElement("w:tblInd")
        tblPr.append(tblInd)
    tblInd.set(qn("w:type"), "dxa")
    tblInd.set(qn("w:w"), "0")


def set_table_borders(table, *, color_hex: str = "A6A6A6") -> None:
    color_hex = s(color_hex).replace("#", "") or "A6A6A6"
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
        el.set(qn("w:sz"), "8")
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


def set_cell_margins(cell, top_dxa: int, bottom_dxa: int, left_dxa: int, right_dxa: int) -> None:
    """
    DXA margins. Uses start/end to be RTL-friendly.
    """
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

    _set("top", int(top_dxa))
    _set("bottom", int(bottom_dxa))
    _set("start", int(left_dxa))
    _set("end", int(right_dxa))


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


def set_repeat_table_header(row) -> None:
    """
    Repeat this row as table header on next page(s).
    """
    tr = row._tr
    trPr = tr.get_or_add_trPr()
    tblHeader = trPr.find(qn("w:tblHeader"))
    if tblHeader is None:
        tblHeader = OxmlElement("w:tblHeader")
        trPr.append(tblHeader)
    tblHeader.set(qn("w:val"), "true")


def set_table_columns_exact(table, widths_in: List[float]) -> None:
    """
    Lock grid columns precisely (in inches).
    """
    tbl = table._tbl
    tblGrid = tbl.tblGrid
    gridCols = tblGrid.findall(qn("w:gridCol"))

    while len(gridCols) < len(widths_in):
        gc = OxmlElement("w:gridCol")
        tblGrid.append(gc)
        gridCols = tblGrid.findall(qn("w:gridCol"))

    for i, w_in in enumerate(widths_in):
        w_emu = int(Inches(float(w_in)).emu)
        w_tw = _emu_to_twips(w_emu)
        gridCols[i].set(qn("w:w"), str(w_tw))


def write_cell_text(
    cell,
    text: Any,
    *,
    font: str = "Times New Roman",
    size: int = 11,
    bold: bool = False,
    align=WD_ALIGN_PARAGRAPH.LEFT,
) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    tight_paragraph(p, align=align, before_pt=0, after_pt=0, line_spacing=1.0)
    r = p.add_run(s(text))
    set_run(r, font, size, bold=bold)


# -------------------------
# Formatting helpers
# -------------------------
def na_if_empty(v: Any) -> str:
    sv = s(v)
    return sv if sv else "N/A"


def format_af_phone(v: Any) -> str:
    sv = s(v)
    if not sv:
        return ""
    digits = re.sub(r"\D+", "", sv)

    if len(digits) == 10 and digits.startswith("0"):
        return "+93" + digits[1:]
    if digits.startswith("93") and len(digits) in (11, 12):
        return "+" + digits
    if sv.startswith("+"):
        return sv
    return sv


def normalize_email_or_na_strict(v: Any) -> str:
    sv = s(v)
    if not sv:
        return "N/A"
    sv = sv.strip()
    if "@" not in sv or "." not in sv.split("@")[-1]:
        return "N/A"
    return sv


def donor_upper_and_pipe(v: Any) -> str:
    sv = s(v)
    if not sv:
        return ""
    sv = sv.replace("/", "|").replace(",", "|").replace(";", "|")
    parts = [p.strip() for p in sv.split("|") if p.strip()]
    return " | ".join([p.upper() for p in parts])


def format_date_dd_mon_yyyy(value: Any) -> str:
    sv = s(value)
    if not sv:
        return ""
    sv_clean = sv.split(".")[0].replace("T", " ").replace("Z", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(sv_clean, fmt).strftime("%d/%b/%Y")
        except Exception:
            pass
    return sv.split(" ")[0] if " " in sv else sv


# -------------------------
# Checkbox rendering helpers
# -------------------------
def _checkbox(checked: bool) -> str:
    return "☒" if checked else "☐"


def three_option_checkbox_line(value: Any, opt1: str, opt2: str, opt3: str) -> str:
    sv = s(value).lower()

    def match(opt: str) -> bool:
        o = opt.lower().strip()
        return sv == o or (sv and o in sv)

    c1 = match(opt1)
    c2 = match(opt2)
    c3 = match(opt3)
    return f"{_checkbox(c1)} {opt1}   {_checkbox(c2)} {opt2}   {_checkbox(c3)} {opt3}"


def write_yes_no_checkboxes(
    cell,
    value: Any,
    *,
    font_size: int = 11,
    align=WD_ALIGN_PARAGRAPH.LEFT,
    font: str = "Times New Roman",
) -> None:
    b = parse_bool_like(value)
    yes = (b is True)
    no = (b is False)

    cell.text = ""
    p = cell.paragraphs[0]
    tight_paragraph(p, align=align, before_pt=0, after_pt=0, line_spacing=1.0)
    r = p.add_run(f"{_checkbox(yes)} Yes   {_checkbox(no)} No")
    set_run(r, font, font_size, bold=False)


def write_two_option_checkboxes(
    cell,
    value: Any,
    opt1: str,
    opt2: str,
    *,
    font_size: int = 11,
    align=WD_ALIGN_PARAGRAPH.LEFT,
    font: str = "Times New Roman",
) -> None:
    sv = s(value).lower().strip()
    o1 = opt1.lower().strip()
    o2 = opt2.lower().strip()

    c1 = bool(sv) and (sv == o1 or o1 in sv)
    c2 = bool(sv) and (sv == o2 or o2 in sv)

    cell.text = ""
    p = cell.paragraphs[0]
    tight_paragraph(p, align=align, before_pt=0, after_pt=0, line_spacing=1.0)
    r = p.add_run(f"{_checkbox(c1)} {opt1}   {_checkbox(c2)} {opt2}")
    set_run(r, font, font_size, bold=False)


# ============================================================
# ✅ FIXED: borderless inner table + no empty first row
# ============================================================
def add_available_documents_inner_table(cell, row: Dict[str, Any], data_keys: Dict[str, str]) -> None:
    """
    Creates a small inner table listing available documents with Yes/No checkboxes.

    FIXES:
      - No extra blank first row (rows=len(docs))
      - Inner table has NO borders (uses parent cell/table border)
      - Keeps layout stable via fixed layout + grid column widths
    """
    cell.text = ""

    docs: List[Tuple[str, Any]] = [
        ("Contract", row.get(data_keys.get("DOC_CONTRACT", ""), row.get("B3_Contract"))),
        ("Journal", row.get(data_keys.get("DOC_JOURNAL", ""), row.get("B4_Journal"))),
        ("BOQ", row.get(data_keys.get("DOC_BOQ", ""), row.get("D2_boq_available"))),
        ("Design drawings", row.get(data_keys.get("DOC_DRAWINGS", ""), row.get("B1_Design_drawings"))),
        ("Site engineer", row.get(data_keys.get("DOC_SITE_ENGINEER", ""), row.get("B6_Site_engineer"))),
        ("Geophysical tests", row.get(data_keys.get("DOC_GEOPHYSICAL", ""), row.get("D3_geophysical_tests_available"))),
        ("Water quality tests", row.get(data_keys.get("DOC_WQ_TEST", ""), row.get("D4_water_quality_tests_available"))),
        ("Pump test results", row.get(data_keys.get("DOC_PUMP_TEST", ""), row.get("D4_pump_test_results_available"))),
    ]

    inner = cell.add_table(rows=len(docs), cols=2)
    inner.autofit = False
    inner.alignment = WD_TABLE_ALIGNMENT.LEFT

    set_table_fixed_layout(inner)

    # Remove borders completely (outer + inner)
    tbl = inner._tbl
    tbl_pr = tbl.tblPr
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)

    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            borders.append(el)
        el.set(qn("w:val"), "nil")

    # Lock inner grid columns (document list wider)
    try:
        set_table_columns_exact(inner, [3.2, 1.2])
    except Exception:
        pass

    for i, (label, val) in enumerate(docs):
        r = inner.rows[i]
        c0, c1 = r.cells[0], r.cells[1]

        c0.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        c1.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        # modest padding so content isn't glued to borders
        set_cell_margins(c0, 40, 40, 80, 80)
        set_cell_margins(c1, 40, 40, 80, 80)

        write_cell_text(c0, label, font="Times New Roman", size=11, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT)

        available = _truthy_doc(val)
        c1.text = ""
        p = c1.paragraphs[0]
        tight_paragraph(p, align=WD_ALIGN_PARAGRAPH.LEFT, before_pt=0, after_pt=0, line_spacing=1.0)
        rrun = p.add_run(f"{_checkbox(available)} Yes   {_checkbox(not available)} No")
        set_run(rrun, "Times New Roman", 11, bold=False)


# -------------------------
# Section-specific style only
# -------------------------
TITLE_TEXT = "1.  General Project Information:"
TITLE_FONT = "Cambria"
TITLE_SIZE = 16
TITLE_BLUE = RGBColor(0, 112, 192)

BODY_FONT = "Times New Roman"
BODY_SIZE = 11

FIELD_FILL_HEX = "D9E2F3"
HEADER_FILL_HEX = "E7EEF9"
BORDER_HEX = "A6A6A6"

FIELD_COL_WIDTH_IN = 2.30

M_TOP = 80
M_BOTTOM = 80
M_LEFT = 120
M_RIGHT = 120

DATA_KEYS = {
    "PROVINCE": "A01_Province",
    "DISTRICT": "A02_District",
    "VILLAGE": "Village",
    "GPS_LAT": "GPS_1-Latitude",
    "GPS_LON": "GPS_1-Longitude",
    "STARTTIME": "starttime",
    "ACTIVITY_NAME": "Activity_Name",
    "PRIMARY_PARTNER": "Primary_Partner_Name",
    "MONITOR_NAME": "A07_Monitor_name",
    "MONITOR_EMAIL": "A12_Monitor_email",
    "RESPONDENT_NAME": "A08_Respondent_name",
    "RESPONDENT_PHONE": "A10_Respondent_phone",
    "RESPONDENT_EMAIL": "A11_Respondent_email",
    "RESPONDENT_SEX": "A09_Respondent_sex",
    "PROJECT_COST_LABEL": "A14_Estimated_cost_amount_label",
    "EST_COST_AMOUNT": "Estimated_Project_Cost_amount",
    "CONTRACT_COST_AMOUNT": "Contracted_Project_Cost_amount",
    "PROJECT_STATUS_LABEL": "Project_Status",
    "PROJECT_PROGRESS_LABEL": "Project_progress",
    "START_DATE": "A15_Contract_start_date",
    "END_DATE": "A16_Contract_end_date",
    "PREV_PROGRESS": "A17_Previous_physical_progress",
    "CURR_PROGRESS": "A18_Current_physical_progress",
    "DONOR_NAME": "A24_Donor_name",
    "MONITORING_REPORT_NO": "A25_Monitoring_report_number",
    "CURRENT_REPORT_DATE": "A20_Current_report_date",
    "PREV_REPORT_DATE": "A21_Last_report_date",
    "VISIT_NO": "A26_Visit_number",
    "DOC_CONTRACT": "B3_Contract",
    "DOC_JOURNAL": "B4_Journal",
    "DOC_BOQ": "D2_boq_available",
    "DOC_DRAWINGS": "B1_Design_drawings",
    "DOC_SITE_ENGINEER": "B6_Site_engineer",
    "DOC_GEOPHYSICAL": "D3_geophysical_tests_available",
    "DOC_WQ_TEST": "D4_water_quality_tests_available",
    "DOC_PUMP_TEST": "D4_pump_test_results_available",
    "COMMUNITY_AGREEMENT": "community_agreement",
    "WORK_SAFETY": "work_safety_considered",
    "ENV_RISK": "environmental_risk",
}


def _set_a4_narrow(section) -> None:
    """A4 + Word 'Narrow' margins (0.5 inch = 12.7mm)."""
    section.page_width = Mm(210)
    section.page_height = Mm(297)

    section.top_margin = Mm(12.7)
    section.bottom_margin = Mm(12.7)
    section.left_margin = Mm(12.7)
    section.right_margin = Mm(12.7)

    section.header_distance = Mm(5)
    section.footer_distance = Mm(5)


def _usable_width_inches(section) -> float:
    usable_emu = section.page_width.emu - section.left_margin.emu - section.right_margin.emu
    return float(usable_emu) / 914400.0


def add_general_project_information(
    doc: Document,
    row: Dict[str, Any],
    overrides: Optional[Dict[str, Any]] = None,
    respondent_sex_val: Any = None,
) -> None:
    overrides = overrides or {}
    row = row or {}

    doc.add_section(WD_SECTION.NEW_PAGE)
    section = doc.sections[-1]
    _set_a4_narrow(section)

    add_section_title_h1(
        doc,
        TITLE_TEXT,
        font=TITLE_FONT,
        size=TITLE_SIZE,
        color=TITLE_BLUE,
        orange_hex="ED7D31",
        after_pt=6,
    )

    province = s(overrides.get("Province", row.get(DATA_KEYS["PROVINCE"])))
    district = s(overrides.get("District", row.get(DATA_KEYS["DISTRICT"])))
    village = s(overrides.get("Village / Community", row.get(DATA_KEYS["VILLAGE"])))

    gps_lat = s(row.get(DATA_KEYS["GPS_LAT"]))
    gps_lon = s(row.get(DATA_KEYS["GPS_LON"]))

    project_name = s(overrides.get("Project Name", row.get(DATA_KEYS["ACTIVITY_NAME"])))
    visit_date = s(overrides.get("Date of Visit", format_date_dd_mon_yyyy(row.get(DATA_KEYS["STARTTIME"]))))
    ip_name = s(overrides.get("Name of the IP, Organization / NGO", row.get(DATA_KEYS["PRIMARY_PARTNER"])))

    monitor_name = s(overrides.get("Name of the monitor Engineer", row.get(DATA_KEYS["MONITOR_NAME"])))
    monitor_email = s(overrides.get("Email of the monitor engineer", row.get(DATA_KEYS["MONITOR_EMAIL"])))

    respondent_name = s(overrides.get("Name of the respondent (Participant / UNICEF / IPs)", row.get(DATA_KEYS["RESPONDENT_NAME"])))
    respondent_phone = s(overrides.get("Contact Number of the Respondent", format_af_phone(row.get(DATA_KEYS["RESPONDENT_PHONE"]))))
    respondent_email = s(overrides.get("Email Address of the Respondent", normalize_email_or_na_strict(row.get(DATA_KEYS["RESPONDENT_EMAIL"]))))

    cost_label = s(row.get(DATA_KEYS["PROJECT_COST_LABEL"])).lower()
    estimated_amount = s(row.get(DATA_KEYS["EST_COST_AMOUNT"]))
    contracted_amount = s(row.get(DATA_KEYS["CONTRACT_COST_AMOUNT"]))
    estimated_cost = estimated_amount if "estimated" in cost_label else ""
    contracted_cost = contracted_amount if "contract" in cost_label else ""

    project_status_val = overrides.get("Project Status", row.get(DATA_KEYS["PROJECT_STATUS_LABEL"]))
    project_status = three_option_checkbox_line(project_status_val, "Ongoing", "Completed", "Suspended")

    reason_delay = s(overrides.get("Reason for delay", na_if_empty(row.get("B8_Reasons_for_delay"))))

    progress_val = overrides.get("Project progress", row.get(DATA_KEYS["PROJECT_PROGRESS_LABEL"]))
    project_progress = three_option_checkbox_line(progress_val, "Ahead of Schedule", "On Schedule", "Running behind")

    contract_start = s(overrides.get("Contract Start Date", format_date_dd_mon_yyyy(row.get(DATA_KEYS["START_DATE"]))))
    contract_end = s(overrides.get("Contract End Date", format_date_dd_mon_yyyy(row.get(DATA_KEYS["END_DATE"]))))

    prev_phys = s(overrides.get("Previous Physical Progress (%)", row.get(DATA_KEYS["PREV_PROGRESS"])))
    curr_phys = s(overrides.get("Current Physical Progress (%)", row.get(DATA_KEYS["CURR_PROGRESS"])))

    cdc_code = s(overrides.get("CDC Code", row.get("A23_CDC_code", "")))
    donor_name = donor_upper_and_pipe(overrides.get("Donor Name", row.get(DATA_KEYS["DONOR_NAME"])))

    monitoring_report_no = s(overrides.get("Monitoring Report Number", row.get(DATA_KEYS["MONITORING_REPORT_NO"])))
    current_report_date = s(overrides.get("Date of Current Report", format_date_dd_mon_yyyy(row.get(DATA_KEYS["CURRENT_REPORT_DATE"]))))

    last_report_date = s(overrides.get("Date of Last Monitoring Report", format_date_dd_mon_yyyy(row.get(DATA_KEYS["PREV_REPORT_DATE"]))))
    sites_visited = s(overrides.get("Number of Sites Visited", row.get(DATA_KEYS["VISIT_NO"])))

    community_agreement = overrides.get(
        "community agreement - Is the community/user group agreed on the well site?",
        row.get(DATA_KEYS["COMMUNITY_AGREEMENT"]) or row.get("Community_agreement"),
    )
    work_safety = overrides.get("Is work_safety_considered -", row.get(DATA_KEYS["WORK_SAFETY"]))
    env_risk = overrides.get("environmental risk -", row.get(DATA_KEYS["ENV_RISK"]))

    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.style = "Table Grid"

    set_table_fixed_layout(table)
    set_table_borders(table, color_hex=BORDER_HEX)

    usable_w_in = _usable_width_inches(section)
    set_table_width_exact(table, Inches(usable_w_in))

    field_in = min(float(FIELD_COL_WIDTH_IN), max(1.0, usable_w_in - 1.0))
    detail_in = max(0.75, usable_w_in - field_in)

    field_w = Inches(field_in)
    detail_w = Inches(detail_in)

    set_table_columns_exact(table, [field_in, detail_in])
    table.columns[0].width = field_w
    table.columns[1].width = detail_w

    hdr = table.rows[0]
    set_row_cant_split(hdr, cant_split=True)
    set_repeat_table_header(hdr)

    for i, txt in enumerate(("Field", "Details")):
        cell = hdr.cells[i]
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        shade_cell(cell, HEADER_FILL_HEX)
        set_cell_margins(cell, M_TOP, M_BOTTOM, M_LEFT, M_RIGHT)
        write_cell_text(cell, txt, font=BODY_FONT, size=BODY_SIZE, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT)

    def _lock_widths_again() -> None:
        set_table_columns_exact(table, [field_in, detail_in])

    def add_row(field: str, value: Any) -> None:
        r = table.add_row()
        set_row_cant_split(r, cant_split=False)

        c0, c1 = r.cells[0], r.cells[1]
        c0.width = field_w
        c1.width = detail_w

        c0.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        shade_cell(c0, FIELD_FILL_HEX)
        set_cell_margins(c0, M_TOP, M_BOTTOM, M_LEFT, M_RIGHT)
        write_cell_text(c0, field, font=BODY_FONT, size=BODY_SIZE, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT)

        c1.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        set_cell_margins(c1, M_TOP, M_BOTTOM, M_LEFT, M_RIGHT)
        write_cell_text(c1, s(value), font=BODY_FONT, size=BODY_SIZE, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT)

        _lock_widths_again()

    def add_row_custom(field: str, renderer) -> None:
        r = table.add_row()
        set_row_cant_split(r, cant_split=False)

        c0, c1 = r.cells[0], r.cells[1]
        c0.width = field_w
        c1.width = detail_w

        c0.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        shade_cell(c0, FIELD_FILL_HEX)
        set_cell_margins(c0, M_TOP, M_BOTTOM, M_LEFT, M_RIGHT)
        write_cell_text(c0, field, font=BODY_FONT, size=BODY_SIZE, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT)

        c1.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        set_cell_margins(c1, M_TOP, M_BOTTOM, M_LEFT, M_RIGHT)
        c1.text = ""
        renderer(c1)

        _lock_widths_again()

    add_row("Province", province)
    add_row("District", district)
    add_row("Village / Community", village)
    add_row("GPS points", f"{gps_lat}, {gps_lon}".strip().strip(","))
    add_row("Project Name", project_name)
    add_row("Date of Visit", visit_date)
    add_row("Name of the IP, Organization / NGO", ip_name)
    add_row("Name of the monitor Engineer", monitor_name)
    add_row("Email of the monitor engineer", monitor_email)
    add_row("Name of the respondent (Participant / UNICEF / IPs)", respondent_name)

    if respondent_sex_val is None:
        respondent_sex_val = overrides.get("Sex of Respondent", row.get(DATA_KEYS["RESPONDENT_SEX"]))

    add_row_custom(
        "Sex of Respondent",
        lambda cell: write_two_option_checkboxes(cell, respondent_sex_val, "Male", "Female", font_size=BODY_SIZE),
    )

    add_row("Contact Number of the Respondent", respondent_phone)
    add_row("Email Address of the Respondent", respondent_email)
    add_row("Estimated Project Cost", na_if_empty(estimated_cost))
    add_row("Contracted Project Cost", na_if_empty(contracted_cost))
    add_row("Project Status", project_status)
    add_row("Reason for delay", reason_delay)
    add_row("Project progress", project_progress)
    add_row("Contract Start Date", na_if_empty(contract_start))
    add_row("Contract End Date", na_if_empty(contract_end))
    add_row("Previous Physical Progress (%)", na_if_empty(prev_phys))
    add_row("Current Physical Progress (%)", na_if_empty(curr_phys))
    add_row("CDC Code", cdc_code)
    add_row("Donor Name", donor_name)
    add_row("Monitoring Report Number", monitoring_report_no)
    add_row("Date of Current Report", current_report_date)
    add_row("Date of Last Monitoring Report", na_if_empty(last_report_date))
    add_row("Number of Sites Visited", sites_visited)

    add_row_custom("Available documents in the site", lambda cell: add_available_documents_inner_table(cell, row, DATA_KEYS))

    add_row_custom(
        "community agreement - Is the community/user group agreed on the well site?",
        lambda cell: write_yes_no_checkboxes(cell, community_agreement, font_size=BODY_SIZE, align=WD_ALIGN_PARAGRAPH.LEFT),
    )
    add_row_custom(
        "Is work_safety_considered -",
        lambda cell: write_yes_no_checkboxes(cell, work_safety, font_size=BODY_SIZE, align=WD_ALIGN_PARAGRAPH.LEFT),
    )
    add_row_custom(
        "environmental risk -",
        lambda cell: write_yes_no_checkboxes(cell, env_risk, font_size=BODY_SIZE, align=WD_ALIGN_PARAGRAPH.LEFT),
    )
