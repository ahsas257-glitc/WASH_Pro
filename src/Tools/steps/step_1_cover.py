from __future__ import annotations

import os
import tempfile
import hashlib
import re
import base64
from io import BytesIO
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List, Callable

import streamlit as st
from PIL import Image
from docx import Document

from src.Tools.utils.types import Tool6Context
from src.report_sections.cover_page import add_cover_page
from design.components.base_tool_ui import card_open, card_close, status_card

# ============================================================
# Session keys (Step 1 only)
# ============================================================
SS_COVER_OVERRIDES = "cover_table_overrides"
SS_COVER_DATE_FMT = "cover_date_format"
SS_COVER_UPLOAD_BYTES = "cover_upload_bytes"

SS_PHOTO_SELECTIONS = "photo_selections"
SS_PHOTO_BYTES = "photo_bytes"       # ✅ keep ONLY full bytes for selected cover (for docx)
SS_PHOTO_FIELD = "photo_field"

# Cover picker state + thumbnails
SS_COVER_SELECTED_URL = "Tools_cover_selected_url"
SS_COVER_PICK_LOCKED = "Tools_cover_pick_locked"
SS_COVER_THUMBS = "Tools_cover_thumbs"          # url -> jpeg thumb bytes (fast grid)
SS_COVER_PICK_PAGE = "Tools_cover_pick_page"
SS_COVER_PICK_SEARCH = "Tools_cover_pick_search"

# (performance helpers)
SS_PREVIEW_DOCX_HASH = "Tools_cover_preview_docx_hash"
SS_PREVIEW_DOCX_BYTES = "Tools_cover_preview_docx_bytes"
SS_PREVIEW_PNG_HASH = "Tools_cover_preview_png_hash"
SS_PREVIEW_PNG_BYTES = "Tools_cover_preview_png_bytes"

# ============================================================
# FIXED THUMB SIZE (consistent grid)
# ============================================================
THUMB_W = 520     # fixed width in px (thumb bytes)
THUMB_H = 360     # fixed height in px (thumb bytes)
THUMB_ASPECT = THUMB_W / THUMB_H

# How many thumbs per page (keep low for speed)
THUMBS_PER_PAGE = 12  # fast load + mobile friendly


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

    tools_name = s(
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
        "Type of Intervention": tools_name,
        "Province / District / Village": location,
        "Date of Visit": date_formatted,
        "Implementing Partner (IP)": ip,
        "Prepared by": DEFAULT_PREPARED_BY,
        "Prepared for": DEFAULT_PREPARED_FOR,
    }


# -----------------------
# URL filtering (images only)
# -----------------------
_IMG_EXT_RE = re.compile(r"\.(jpg|jpeg|png|webp|gif|bmp|tif|tiff)(\?|#|$)", re.IGNORECASE)
_AUD_EXT_RE = re.compile(r"\.(mp3|wav|m4a|aac|ogg|opus|flac)(\?|#|$)", re.IGNORECASE)
_NON_IMG_HINT_RE = re.compile(r"\.(pdf|doc|docx|xls|xlsx|csv|zip|rar)(\?|#|$)", re.IGNORECASE)

def _looks_like_image_url(url: str, label: str = "") -> bool:
    u = s(url)
    if not u:
        return False
    low_u = u.lower()
    low_l = s(label).lower()

    if _NON_IMG_HINT_RE.search(low_u):
        return False
    if _AUD_EXT_RE.search(low_u):
        return False
    if _IMG_EXT_RE.search(low_u):
        return True

    # extension-less but image-ish sources
    if "googleusercontent.com" in low_u or "lh3.googleusercontent.com" in low_u:
        return True
    if "photo" in low_l or "image" in low_l or "picture" in low_l:
        return True
    return False


def _filter_photo_urls(urls: List[str], labels: Dict[str, str]) -> List[str]:
    out: List[str] = []
    for u in (urls or []):
        if not s(u):
            continue
        lab = s(labels.get(u, ""))
        if _looks_like_image_url(u, lab):
            out.append(u)

    seen = set()
    res: List[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            res.append(u)
    return res


# ============================================================
# FAST thumbnail: fixed size + crop to aspect + JPEG
# ============================================================
def _crop_to_aspect(img: Image.Image, target_aspect: float) -> Image.Image:
    w, h = img.size
    if w <= 0 or h <= 0:
        return img
    cur = w / h
    if abs(cur - target_aspect) < 1e-3:
        return img
    if cur > target_aspect:
        # too wide -> crop width
        new_w = int(h * target_aspect)
        left = max(0, (w - new_w) // 2)
        return img.crop((left, 0, left + new_w, h))
    # too tall -> crop height
    new_h = int(w / target_aspect)
    top = max(0, (h - new_h) // 2)
    return img.crop((0, top, w, top + new_h))


def _make_fixed_thumb(img_bytes: bytes) -> Optional[bytes]:
    """
    Output: JPEG thumb at exactly THUMB_W x THUMB_H
    """
    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        img = _crop_to_aspect(img, THUMB_ASPECT)
        img = img.resize((THUMB_W, THUMB_H))
        out = BytesIO()
        img.save(out, format="JPEG", quality=70, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("utf-8")


def _render_thumb_html(thumb_bytes: bytes, caption: str) -> None:
    """
    HTML img with fixed height + object-fit cover
    """
    if not thumb_bytes:
        st.caption("Preview not available")
        return
    uri = "data:image/jpeg;base64," + _b64(thumb_bytes)
    cap = s(caption)
    st.markdown(
        f"""
        <div class="t6-cover-card">
          <img class="t6-cover-img" src="{uri}" />
          <div class="t6-cover-cap">{cap}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# State
# ============================================================
def _ensure_cover_state(ctx: Tool6Context) -> None:
    st.session_state.setdefault(SS_PHOTO_SELECTIONS, {})
    st.session_state.setdefault(SS_PHOTO_BYTES, {})   # full bytes only for selected cover
    st.session_state.setdefault(SS_PHOTO_FIELD, {})
    st.session_state.setdefault(SS_COVER_UPLOAD_BYTES, None)
    st.session_state.setdefault(SS_COVER_DATE_FMT, "%d/%b/%Y")

    st.session_state.setdefault(SS_COVER_SELECTED_URL, None)
    st.session_state.setdefault(SS_COVER_PICK_LOCKED, False)
    st.session_state.setdefault(SS_COVER_THUMBS, {})
    st.session_state.setdefault(SS_COVER_PICK_PAGE, 1)
    st.session_state.setdefault(SS_COVER_PICK_SEARCH, "")

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


# ============================================================
# Preview builders (unchanged)
# ============================================================
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
    if not cover_img:
        return None
    table_items = tuple(sorted((k, s(v)) for k, v in (table_vals or {}).items()))
    fp = repr((_sha1(cover_img), table_items)).encode("utf-8")
    h = _sha1(fp)

    if st.session_state.get(SS_PREVIEW_DOCX_HASH) == h and st.session_state.get(SS_PREVIEW_DOCX_BYTES):
        return st.session_state[SS_PREVIEW_DOCX_BYTES]

    try:
        docx_bytes = _build_cover_preview_docx_bytes(ctx, cover_image_bytes=cover_img, cover_table_values=table_vals)
    except Exception:
        return None

    st.session_state[SS_PREVIEW_DOCX_HASH] = h
    st.session_state[SS_PREVIEW_DOCX_BYTES] = docx_bytes
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
# FAST THUMB cache (thumb only for grid)
# ============================================================
def _fetch_and_cache_thumb_only(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    url = s(url)
    if not url:
        return
    thumbs: Dict[str, bytes] = st.session_state.get(SS_COVER_THUMBS, {}) or {}
    if url in thumbs and thumbs[url]:
        return

    ok, data, _msg = fetch_image(url)
    if not (ok and data):
        return

    th = _make_fixed_thumb(data)
    if th:
        thumbs[url] = th
        st.session_state[SS_COVER_THUMBS] = thumbs


def _ensure_full_bytes_for_selected(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    """
    Full bytes فقط برای cover انتخاب‌شده.
    """
    url = s(url)
    if not url:
        return
    full: Dict[str, bytes] = st.session_state.get(SS_PHOTO_BYTES, {}) or {}
    if url in full and full[url]:
        return
    ok, data, _msg = fetch_image(url)
    if ok and data:
        full[url] = data
        st.session_state[SS_PHOTO_BYTES] = full


# ============================================================
# Cover picker (FAST + fixed size + responsive)
# ============================================================
def _cover_picker_grid(
    *,
    urls: List[str],
    labels: Dict[str, str],
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> Optional[str]:
    locked = bool(st.session_state.get(SS_COVER_PICK_LOCKED))
    selected_url = st.session_state.get(SS_COVER_SELECTED_URL)

    def _lab(u: str) -> str:
        return s(labels.get(u, u))

    thumbs: Dict[str, bytes] = st.session_state.get(SS_COVER_THUMBS, {}) or {}

    # LOCKED: show only selected
    if locked and selected_url:
        st.markdown("✅ **Selected cover**")
        if selected_url not in thumbs:
            _fetch_and_cache_thumb_only(selected_url, fetch_image=fetch_image)
            thumbs = st.session_state.get(SS_COVER_THUMBS, {}) or {}
        th = thumbs.get(selected_url)
        if th:
            _render_thumb_html(th, _lab(selected_url))
        else:
            st.caption(_lab(selected_url))

        c1, c2 = st.columns([0.55, 0.45], gap="small")
        with c1:
            st.caption("Other photos are hidden.")
        with c2:
            if st.button("Change cover", use_container_width=True, key="Tools_cover_change"):
                st.session_state[SS_COVER_PICK_LOCKED] = False
        return selected_url

    # Not locked: Search + pagination
    q = st.text_input(
        "Search cover photos",
        value=s(st.session_state.get(SS_COVER_PICK_SEARCH, "")),
        key="Tools_cover_search",
        placeholder="Type to filter by name...",
        label_visibility="collapsed",
    ).strip().lower()
    st.session_state[SS_COVER_PICK_SEARCH] = q

    if q:
        filtered = [u for u in urls if q in _lab(u).lower()]
    else:
        filtered = list(urls)

    if not filtered:
        st.info("No photos match your search.")
        return None

    total = len(filtered)
    per_page = int(THUMBS_PER_PAGE)
    pages = max(1, (total + per_page - 1) // per_page)

    topA, topB, topC = st.columns([0.33, 0.33, 0.34], gap="small")
    with topA:
        page = st.number_input(
            "Page",
            min_value=1,
            max_value=pages,
            value=int(st.session_state.get(SS_COVER_PICK_PAGE, 1) or 1),
            step=1,
            key="Tools_cover_page",
            label_visibility="collapsed",
        )
        st.session_state[SS_COVER_PICK_PAGE] = int(page)
    with topB:
        st.caption(f"{total} photo(s)")
    with topC:
        if st.button("Reset search", use_container_width=True, key="Tools_cover_reset"):
            st.session_state[SS_COVER_PICK_SEARCH] = ""
            st.session_state[SS_COVER_PICK_PAGE] = 1
            st.rerun()

    start = (int(page) - 1) * per_page
    end = min(total, start + per_page)
    chunk = filtered[start:end]

    # ✅ Prefetch thumbs for this page (no spinner)
    for u in chunk:
        if u not in thumbs:
            _fetch_and_cache_thumb_only(u, fetch_image=fetch_image)
    thumbs = st.session_state.get(SS_COVER_THUMBS, {}) or {}

    # Grid: 3 columns (Responsive: Streamlit stacks automatically on mobile)
    cols = 3
    rows = [chunk[i:i + cols] for i in range(0, len(chunk), cols)]
    for r in rows:
        grid = st.columns(cols, gap="small")
        for i, u in enumerate(r):
            with grid[i]:
                th = thumbs.get(u)
                if th:
                    _render_thumb_html(th, _lab(u))
                else:
                    st.caption("Preview not available")
                    st.caption(_lab(u))

                if st.button("Select", use_container_width=True, key=f"Tools_cover_pick_{_sha1(u.encode('utf-8'))}"):
                    st.session_state[SS_COVER_SELECTED_URL] = u
                    selected_url = u
                    st.rerun()

    # Confirm section
    if selected_url:
        st.divider()
        st.markdown("### Confirm cover")
        if selected_url not in thumbs:
            _fetch_and_cache_thumb_only(selected_url, fetch_image=fetch_image)
            thumbs = st.session_state.get(SS_COVER_THUMBS, {}) or {}
        th = thumbs.get(selected_url)
        if th:
            _render_thumb_html(th, _lab(selected_url))

        c1, c2 = st.columns([0.6, 0.4], gap="small")
        with c1:
            if st.button("✅ Use this cover (hide others)", use_container_width=True, key="Tools_cover_lock"):
                st.session_state[SS_COVER_PICK_LOCKED] = True
                st.rerun()
        with c2:
            st.caption("After confirm, others will be hidden.")

        return selected_url

    return None


# ============================================================
# MAIN RENDER
# ============================================================
def render_step(ctx: Tool6Context, *, fetch_image) -> bool:
    _ensure_cover_state(ctx)
    cover_table: Dict[str, str] = st.session_state[SS_COVER_OVERRIDES]

    # ✅ CSS for fixed-size thumbnails + responsive look
    st.markdown(
        """
        <style>
          .t6-cover-card { width: 100%; }
          .t6-cover-img {
            width: 100%;
            height: 160px;              /* base height */
            object-fit: cover;
            border-radius: 14px;
            display: block;
          }
          .t6-cover-cap {
            font-size: 12px;
            opacity: 0.85;
            margin-top: 6px;
            line-height: 1.2;
            word-break: break-word;
          }
          /* monitor */
          @media (min-width: 1600px){
            .t6-cover-img { height: 180px; }
            .t6-cover-cap { font-size: 13px; }
          }
          /* mobile */
          @media (max-width: 700px){
            .t6-cover-img { height: 140px; }
            .t6-cover-cap { font-size: 12px; }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        card_open(
            "Cover Page",
            subtitle="Pick a cover image (preview first). After you confirm, other photos are hidden. Then preview the Word cover page.",
            variant="lg-variant-cyan",
        )

        # ------------------------------------------------
        # A) Cover image (FAST GRID)
        # ------------------------------------------------
        col1, col2 = st.columns([1.25, 1], gap="large")

        with col1:
            st.markdown("### 1) Choose cover image (fast preview)")

            all_urls = getattr(ctx, "all_photo_urls", None) or []
            labels = getattr(ctx, "photo_label_by_url", {}) or {}
            image_urls = _filter_photo_urls(all_urls, labels)

            if not image_urls:
                status_card("No photos found", "No image URLs detected for this TPM ID.", level="warning")
            else:
                picked = _cover_picker_grid(urls=image_urls, labels=labels, fetch_image=fetch_image)
                if picked:
                    # ✅ full bytes only for selected cover (fast overall)
                    _ensure_full_bytes_for_selected(picked, fetch_image=fetch_image)

                    st.session_state[SS_PHOTO_FIELD][picked] = labels.get(picked, "Cover Photo")
                    st.session_state[SS_PHOTO_SELECTIONS][picked] = "Cover Page"
                    st.session_state[SS_PHOTO_SELECTIONS] = enforce_single_cover(st.session_state[SS_PHOTO_SELECTIONS])

                    status_card("Cover selected", "This image will be used on the cover page.", level="success")

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
        # B) Cover table + date format options
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
                    cover_table["Project Title"] = st.text_area("Project Title", value=s(cover_table.get("Project Title")), height=70)
                    cover_table["Visit No."] = st.text_input("Visit No.", value=s(cover_table.get("Visit No.")))
                    cover_table["Type of Intervention"] = st.text_input("Type of Intervention", value=s(cover_table.get("Type of Intervention")))
                    cover_table["Date of Visit"] = st.text_input(
                        "Date of Visit",
                        value=s(cover_table.get("Date of Visit")),
                        help="You can override the formatted date manually if needed.",
                    )

                with cB:
                    cover_table["Province / District / Village"] = st.text_area(
                        "Province / District / Village",
                        value=s(cover_table.get("Province / District / Village")),
                        height=70,
                    )
                    cover_table["Implementing Partner (IP)"] = st.text_area("Implementing Partner (IP)", value=s(cover_table.get("Implementing Partner (IP)")), height=70)
                    cover_table["Prepared by"] = st.text_input("Prepared by", value=s(cover_table.get("Prepared by")) or DEFAULT_PREPARED_BY)
                    cover_table["Prepared for"] = st.text_input("Prepared for", value=s(cover_table.get("Prepared for")) or DEFAULT_PREPARED_FOR)

                if st.form_submit_button("Save cover table"):
                    st.session_state[SS_COVER_OVERRIDES] = dict(cover_table)
                    status_card("Saved", "Cover table updated successfully.", level="success")

        st.divider()

        # ------------------------------------------------
        # C) Preview (Word-like) - cached
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
