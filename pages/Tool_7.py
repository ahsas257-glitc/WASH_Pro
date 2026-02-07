from __future__ import annotations

import os
import re
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from urllib.parse import urlparse

import requests
import streamlit as st
from PIL import Image

# ============================================================
# Page config (MUST BE FIRST Streamlit call)
# ============================================================
st.set_page_config(page_title="Tool 7 — WASH Report Generator", layout="wide")

# Robust project root: /pages/Tool_7.py -> project root is parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root = str(PROJECT_ROOT)

# ============================================================
# Internal project imports (DO NOT REMOVE)
# ============================================================
from src.config import GOOGLE_SHEET_ID, TPM_COL
from src.data_processing import get_row_cached
from src.report_builder import build_tool6_full_report_docx
from src.ui.wizard import Wizard, WizardConfig
from src.integrations.surveycto_client import (
    surveycto_login_ui,
    load_auth_state,
    surveycto_request,
)

# ✅ single source of design
from design.components.base_tool_ui import (
    apply_global_background,
    topbar,
    status_card,
)

# ✅ Tool 7 modules (your structure)
from src.Tools.utils.state import init_tool6_state
from src.Tools.utils.types import Tool6Context
from src.Tools.steps import (
    step_1_cover,
    step_2_general_info,
    step_3_observations,
    step_4_findings_recommendations,
    step_6_executive_summary,
    step_7_data_collection_methods,
)

# Optional steps
try:
    from src.Tools.steps import step_5_work_progress
except Exception:
    step_5_work_progress = None  # type: ignore

try:
    from src.Tools.steps import step_8_summary_of_findings as step_8_summary_ui
except Exception:
    step_8_summary_ui = None  # type: ignore

try:
    from src.Tools.steps import step_9_conclusion as step_9_conclusion_ui
except Exception:
    step_9_conclusion_ui = None  # type: ignore

try:
    from src.Tools.steps import step_10_generate_report
except Exception:
    step_10_generate_report = None  # type: ignore

# ============================================================
# ✅ Apply GLOBAL Liquid-Glass background (Your design)
# ============================================================
apply_global_background(
    logo_path="assets/images/Logo_of_PPC.png",
    logo_opacity_light=0.07,
    logo_opacity_dark=0.12,
    intensity=1.0,
)

# ============================================================
# IMPORTANT: lock TPM ID before any state init resets it
# ============================================================
# Tool pages rely on Home storing this in session_state["tpm_id"]
if "_tpm_id_locked" not in st.session_state:
    st.session_state["_tpm_id_locked"] = st.session_state.get("tpm_id")

# ============================================================
# INIT STATE (may reset keys; we restore tpm_id after)
# ============================================================
init_tool6_state()

# Restore TPM after init (critical fix for: "No TPM ID selected")
if st.session_state.get("tpm_id") in (None, "", False):
    st.session_state["tpm_id"] = st.session_state.get("_tpm_id_locked")

# ============================================================
# Optional: SurveyCTO SDK (kept optional)
# ============================================================
try:
    import pysurveycto  # pip install pysurveycto
    _HAS_PYSURVEYCTO = True
except Exception:
    pysurveycto = None
    _HAS_PYSURVEYCTO = False

# ============================================================
# Google Sheet Column Mapping (KEEP AS IS)
# ============================================================
COL = {
    "PROVINCE": "A01_Province",
    "DISTRICT": "A02_District",
    "VILLAGE": "Village",
    "GPS_LAT": "GPS_1-Latitude",
    "GPS_LON": "GPS_1-Longitude",
    "STARTTIME": "starttime",
    "ACTIVITY_NAME": "Activity_Name",
    "PROJECT_STATUS": "Project_Status",
    "DELAY_REASON": "B8_Reasons_for_delay",
    "PRIMARY_PARTNER": "Primary_Partner_Name",
    "MONITOR_NAME": "A07_Monitor_name",
    "MONITOR_EMAIL": "A12_Monitor_email",
    "RESP_NAME": "A08_Respondent_name",
    "RESP_SEX_LABEL": "A09_Respondent_sex",
    "RESP_PHONE": "A10_Respondent_phone",
    "RESP_EMAIL": "A11_Respondent_email",
    "CDC_CODE": "A23_CDC_code",
    "DONOR_NAME": "A24_Donor_name",
    "REPORT_NUMBER": "A25_Monitoring_report_number",
    "CURRENT_REPORT_DATE": "A20_Current_report_date",
    "VISIT_NUMBER": "A26_Visit_number",
}


def col(row: dict, key: str, default=""):
    return (row or {}).get(COL.get(key, ""), default)


def gps_points_from_row(row: dict) -> str:
    lat = str(col(row, "GPS_LAT", "") or "").strip()
    lon = str(col(row, "GPS_LON", "") or "").strip()
    return f"{lat}, {lon}".strip().strip(",")


# ============================================================
# Small helpers
# ============================================================
def safe_str(x) -> str:
    return "" if x is None else str(x)


def ensure_http(url: str) -> str:
    u = (url or "").strip()
    return u if u.startswith("http") else ""


def na_if_empty_ui(raw) -> str:
    s0 = safe_str(raw).strip()
    return s0 if s0 else "N/A"


def format_af_phone_ui(raw) -> str:
    s0 = re.sub(r"\D+", "", safe_str(raw))
    if not s0:
        return ""
    if s0.startswith("0"):
        s0 = s0[1:]
    if s0.startswith("93"):
        return f"+{s0}"
    return f"+93{s0}"


# ============================================================
# Image safety helpers
# ============================================================
def _looks_like_html(data: bytes) -> bool:
    head = (data or b"")[:300].lower()
    return b"<html" in head or b"<!doctype" in head


def _to_clean_png_bytes(img_bytes: bytes) -> bytes:
    img = Image.open(BytesIO(img_bytes)).convert("RGB")
    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


# ============================================================
# SurveyCTO helpers
# ============================================================
def _is_scto_view_attachment(url: str) -> bool:
    return "surveycto.com/view/submission-attachment" in (url or "").lower()


def _is_surveycto_url(url: str) -> bool:
    try:
        host = (urlparse(url).netloc or "").lower()
        return host.endswith("surveycto.com")
    except Exception:
        return False


def _url_to_scto_path(url: str) -> str:
    p = urlparse(url)
    path = (p.path or "").lstrip("/")
    if p.query:
        path = f"{path}?{p.query}"
    return path


def get_scto_client():
    if not _HAS_PYSURVEYCTO:
        return None
    load_auth_state()
    user = st.session_state.get("scto_username", "").strip()
    pwd = st.session_state.get("scto_password", "").strip()
    if not user or not pwd:
        return None
    try:
        return pysurveycto.SurveyCTOObject("act4performance", user, pwd)
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=3600)
def scto_get_attachment_bytes(url: str, username: str) -> Optional[bytes]:
    scto = get_scto_client()
    if scto is None:
        return None
    try:
        data = scto.get_attachment(url)
        if not data or _looks_like_html(data):
            return None
        return data
    except Exception:
        return None


def _plain_http_get(url: str, *, timeout: int) -> requests.Response:
    return requests.get(url, timeout=timeout, allow_redirects=True)


def _scto_http_get(url: str, *, timeout: int) -> requests.Response:
    path = _url_to_scto_path(url)
    return surveycto_request("GET", path, timeout=timeout)


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_image_cached(url: str, username: str) -> Tuple[bool, Optional[bytes], str]:
    try:
        if not url or not url.startswith("http"):
            return False, None, "Invalid URL"

        if _is_surveycto_url(url):
            if _is_scto_view_attachment(url):
                b = scto_get_attachment_bytes(url, username)
                if b:
                    try:
                        return True, _to_clean_png_bytes(b), "OK"
                    except Exception:
                        return False, None, "Invalid/unsupported image data (SDK)"

            r = _scto_http_get(url, timeout=25)
            if r.status_code >= 400:
                return False, None, f"HTTP {r.status_code}"
            if _looks_like_html(r.content):
                return False, None, "HTML response (auth required)"
            try:
                return True, _to_clean_png_bytes(r.content), "OK"
            except Exception:
                return False, None, "Invalid/unsupported image data"

        r = _plain_http_get(url, timeout=25)
        if r.status_code >= 400:
            return False, None, f"HTTP {r.status_code}"
        if _looks_like_html(r.content):
            return False, None, "HTML response"
        try:
            return True, _to_clean_png_bytes(r.content), "OK"
        except Exception:
            return False, None, "Invalid/unsupported image data"

    except Exception as e:
        return False, None, str(e)


def _cache_user_key() -> str:
    load_auth_state()
    return (st.session_state.get("scto_username") or "").strip() or "anon"


def fetch_image(url: str) -> Tuple[bool, Optional[bytes], str]:
    return fetch_image_cached(url, username=_cache_user_key())


# ============================================================
# Wizard steps (as your step modules expect)
# ============================================================
STEPS = [
    "1) Cover Photo",
    "2) General Info",
    "3) Observations",
    "4) Findings & Recommendations",
    "5) Work Progress Table",
    "6) Executive Summary",
    "7) Data Collection Methods",
    "8) Summary of Findings (UI)",
    "9) Conclusion",
    "10) Generate Report",
]

wiz = Wizard(WizardConfig(tool_name="Tool 7", steps=STEPS, key_prefix="tool7"))

topbar(
    title="Tool 7 — Report Generator",
    subtitle="Auto-filled from Google Sheet + SurveyCTO attachments",
    right_chip="WASH • UNICEF",
)

# MUST stay exactly "Tool 7" for Google Sheet lookup
tool_name = "Tool 7"
tpm_id = st.session_state.get("tpm_id")

if not tpm_id:
    status_card("No TPM ID selected", "Please go back to Home and select a TPM ID.", level="warning")
    st.stop()

status_card("Selected TPM ID", str(tpm_id), level="info")

with st.sidebar:
    logged_in = surveycto_login_ui(in_sidebar=False)

if not logged_in:
    status_card("SurveyCTO login", "Please login via the sidebar to download images from SurveyCTO", level="warning")


@st.cache_data(show_spinner=False, ttl=600)
def _load_tool7_row(sheet_id: str, tool: str, tpm_value: str, tpm_col: str):
    return get_row_cached(sheet_id, tool, tpm_id=tpm_value, tpm_col=tpm_col)


row = _load_tool7_row(GOOGLE_SHEET_ID, tool_name, str(tpm_id), TPM_COL)
if not row:
    status_card("TPM not found", "The selected TPM ID was not found in the Tool 7 worksheet.", level="error")
    st.stop()

# ============================================================
# Logos (safe paths)
# ============================================================
def _safe_logo(path: str) -> Optional[str]:
    return path if path and os.path.exists(path) else None


unicef_logo_path = _safe_logo(os.path.join(project_root, "assets/images/Logo_of_UNICEF.png"))
act_logo_path = _safe_logo(os.path.join(project_root, "assets/images/Logo_of_ACT.png"))
ppc_logo_path = _safe_logo(os.path.join(project_root, "assets/images/Logo_of_PPC.png"))

# ============================================================
# Defaults (from Google Sheet)
# ============================================================
defaults = {
    "Province": col(row, "PROVINCE", ""),
    "District": col(row, "DISTRICT", ""),
    "Village / Community": col(row, "VILLAGE", ""),
    "GPS points": gps_points_from_row(row),
    "Project Name": col(row, "ACTIVITY_NAME", ""),
    "Date of Visit": safe_str(col(row, "STARTTIME", "")).split(" ")[0],

    "Name of the IP, Organization / NGO": col(row, "PRIMARY_PARTNER", ""),
    "Name of the monitor engineer": col(row, "MONITOR_NAME", ""),
    "Email of the monitor engineer": col(row, "MONITOR_EMAIL", ""),

    "Name of the respondent (Participant / UNICEF / IPs)": col(row, "RESP_NAME", ""),
    "Sex of Respondent": col(row, "RESP_SEX_LABEL", ""),
    "Contact Number of the Respondent": format_af_phone_ui(col(row, "RESP_PHONE", "")),
    "Email Address of the Respondent": na_if_empty_ui(col(row, "RESP_EMAIL", "")),

    "Project Status": col(row, "PROJECT_STATUS", ""),
    "Reason for delay": na_if_empty_ui(col(row, "DELAY_REASON", "")),
    "CDC Code": col(row, "CDC_CODE", ""),
    "Donor Name": col(row, "DONOR_NAME", ""),

    "Monitoring Report Number": col(row, "REPORT_NUMBER", ""),
    "Date of Current Report": safe_str(col(row, "CURRENT_REPORT_DATE", "")).split(" ")[0],
    "Number of Sites Visited": col(row, "VISIT_NUMBER", ""),
}

hints = {
    "CDC Code": "Verify against official documentation.",
    "Monitoring Report Number": "Verify before final generation.",
    "Contact Number of the Respondent": "Auto-formatted to +93.",
    "Email Address of the Respondent": "If empty, DOCX shows N/A.",
    "Reason for delay": "If empty, DOCX shows N/A.",
}

st.session_state.setdefault("general_info_overrides", {})
if not st.session_state["general_info_overrides"]:
    st.session_state["general_info_overrides"] = {k: str(v) for k, v in defaults.items()}

# ============================================================
# Media links
# ============================================================
def normalize_media_url(url: str) -> str:
    u = (url or "").strip()
    if not u.startswith("http"):
        return u
    m = re.search(r"drive\.google\.com\/file\/d\/([^\/]+)\/", u)
    if m:
        fid = m.group(1)
        return f"https://drive.google.com/uc?export=download&id={fid}"
    m = re.search(r"drive\.google\.com\/open\?id=([^&]+)", u)
    if m:
        fid = m.group(1)
        return f"https://drive.google.com/uc?export=download&id={fid}"
    return u


def extract_photo_links(row: dict) -> List[Dict[str, str]]:
    links: List[Dict[str, str]] = []
    for k, v in (row or {}).items():
        sv = safe_str(v).strip()
        if not sv.startswith("http"):
            continue

        low = sv.lower()
        is_img = any(ext in low for ext in [".jpg", ".jpeg", ".png", ".webp"])
        is_drive = ("drive.google.com" in low) or ("googleusercontent.com" in low)
        is_scto = "surveycto.com/view/submission-attachment" in low

        if is_img or is_drive or is_scto:
            links.append({"field": k, "url": normalize_media_url(sv)})

    uniq: List[Dict[str, str]] = []
    seen = set()
    for it in links:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        uniq.append(it)
    return uniq


photos = extract_photo_links(row)
photo_label_by_url: Dict[str, str] = {}
for i, p in enumerate(photos or [], start=1):
    u = ensure_http(p.get("url", ""))
    f = p.get("field", "Photo")
    if u:
        photo_label_by_url[u] = f"{i:02d}. {f}"
all_photo_urls = list(photo_label_by_url.keys())

# ============================================================
# DOCX generation helpers (used by Step 10)
# ============================================================
def _resolve_cover_bytes() -> Optional[bytes]:
    return step_1_cover.resolve_cover_bytes()


def _generate_docx() -> bool:
    cover_bytes = _resolve_cover_bytes()
    if cover_bytes is None:
        st.session_state["tool7_docx_bytes"] = None
        return False

    photo_bytes = st.session_state.get("photo_bytes", {})
    component_observations = st.session_state.get("tool7_component_observations_final")
    if component_observations is None:
        component_observations = st.session_state.get("component_observations", [])

    severity_by_no = st.session_state.get("tool7_severity_by_no") or {}
    severity_by_finding = st.session_state.get("tool7_severity_by_finding") or {}
    add_legend = bool(st.session_state.get("tool7_add_legend", True))

    conclusion_payload = st.session_state.get("tool7_conclusion_payload") or {}
    conclusion_text = conclusion_payload.get("conclusion_text")
    key_points = conclusion_payload.get("key_points")
    reco_summary = conclusion_payload.get("recommendations_summary")

    docx_bytes = build_tool6_full_report_docx(
        row=row,
        cover_image_bytes=cover_bytes,
        unicef_logo_path=unicef_logo_path,
        act_logo_path=act_logo_path,
        ppc_logo_path=ppc_logo_path,
        general_info_overrides=st.session_state.get("general_info_overrides", {}),
        component_observations=component_observations,
        photo_bytes=photo_bytes,
        photo_field_map=st.session_state.get("photo_field", {}),
        severity_by_no=severity_by_no,
        severity_by_finding=severity_by_finding,
        add_legend=add_legend,
        conclusion_text=conclusion_text,
        conclusion_key_points=key_points,
        conclusion_recommendations_summary=reco_summary,
        conclusion_section_no="7",
    )

    st.session_state["tool7_docx_bytes"] = docx_bytes
    return True

# ============================================================
# Context object (what all step files expect)
# ============================================================
ctx = Tool6Context(
    project_root=project_root,
    tool_name=tool_name,
    tpm_id=str(tpm_id),
    row=row,
    defaults=defaults,
    hints=hints,
    all_photo_urls=all_photo_urls,
    photo_label_by_url=photo_label_by_url,
    audios=[],
    unicef_logo_path=unicef_logo_path,
    act_logo_path=act_logo_path,
    ppc_logo_path=ppc_logo_path,
)

# ============================================================
# Routing
# ============================================================
wiz.header()
step = wiz.step_idx

if step == 0:
    ok = step_1_cover.render_step(ctx, fetch_image=fetch_image)
    b, n = wiz.nav(can_next=ok, back_label="Back", next_label="Next", generate_label="Generate")
    if b or n:
        st.rerun()
    st.stop()

if step == 1:
    ok = step_2_general_info.render_step(ctx)
    b, n = wiz.nav(can_next=ok, back_label="Back", next_label="Next", generate_label="Generate")
    if b or n:
        st.rerun()
    st.stop()

if step == 2:
    ok = step_3_observations.render_step(ctx, fetch_image=fetch_image)
    b, n = wiz.nav(can_next=ok, back_label="Back", next_label="Next", generate_label="Generate")
    if b or n:
        st.rerun()
    st.stop()

if step == 3:
    ok = step_4_findings_recommendations.render_step(ctx, fetch_image=fetch_image)
    b, n = wiz.nav(can_next=ok, back_label="Back", next_label="Next", generate_label="Generate")
    if b or n:
        st.rerun()
    st.stop()

if step == 4:
    if step_5_work_progress is None:
        status_card("Missing Step 5", "src/Tools/steps/step_5_work_progress.py not found.", level="error")
        st.stop()
    ok = step_5_work_progress.render_step(ctx)
    b, n = wiz.nav(can_next=ok, back_label="Back", next_label="Next", generate_label="Generate")
    if b or n:
        st.rerun()
    st.stop()

if step == 5:
    ok = step_6_executive_summary.render_step(ctx)
    b, n = wiz.nav(can_next=ok, back_label="Back", next_label="Next", generate_label="Generate")
    if b or n:
        st.rerun()
    st.stop()

if step == 6:
    ok = step_7_data_collection_methods.render_step(ctx)
    b, n = wiz.nav(can_next=ok, back_label="Back", next_label="Next", generate_label="Generate")
    if b or n:
        st.rerun()
    st.stop()

if step == 7:
    if step_8_summary_ui is not None:
        ok = step_8_summary_ui.render_step(ctx)
        b, n = wiz.nav(can_next=ok, back_label="Back", next_label="Next", generate_label="Generate")
        if b or n:
            st.rerun()
        st.stop()

    st.subheader("Summary of Findings (UI)")
    st.info("Step 8 UI module is not found. You can still generate DOCX.")
    st.session_state.setdefault("tool7_severity_by_no", {})
    st.session_state.setdefault("tool7_severity_by_finding", {})
    st.session_state.setdefault("tool7_add_legend", True)
    b, n = wiz.nav(can_next=True, back_label="Back", next_label="Next", generate_label="Generate")
    if b or n:
        st.rerun()
    st.stop()

if step == 8:
    if step_9_conclusion_ui is not None:
        ok = step_9_conclusion_ui.render_step(ctx)
        b, n = wiz.nav(can_next=ok, back_label="Back", next_label="Next", generate_label="Generate")
        if b or n:
            st.rerun()
        st.stop()

    st.subheader("Conclusion")
    st.caption("If you don’t have Step 9 module yet, you can still write conclusion here quickly.")

    payload = st.session_state.get("tool7_conclusion_payload") or {}
    txt = st.text_area("Conclusion text", value=str(payload.get("conclusion_text") or ""), height=140)
    kp_raw = st.text_area("Key Points (one per line)", value="\n".join(payload.get("key_points") or []), height=120)
    rec = st.text_area("Recommendations Summary", value=str(payload.get("recommendations_summary") or ""), height=120)

    key_points = [x.strip() for x in kp_raw.split("\n") if x.strip()]
    st.session_state["tool7_conclusion_payload"] = {
        "conclusion_text": txt,
        "key_points": key_points,
        "recommendations_summary": rec,
    }

    b, n = wiz.nav(can_next=True, back_label="Back", next_label="Next", generate_label="Generate")
    if b or n:
        st.rerun()
    st.stop()

if step == 9:
    if step_10_generate_report is None:
        status_card("Missing Step 10", "src/Tools/steps/step_10_generate_report.py not found.", level="error")
        st.stop()

    def _on_generate_docx():
        ok2 = _generate_docx()
        return bool(ok2)

    ok = step_10_generate_report.render_step(
        ctx,
        resolve_cover_bytes=_resolve_cover_bytes,
        on_generate_docx=_on_generate_docx,
    )

    b, n = wiz.nav(can_next=ok, back_label="Back", next_label="Next", generate_label="Generate")
    if b or n:
        st.rerun()
    st.stop()
