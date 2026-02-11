from __future__ import annotations

import base64
import hashlib
import re
import time
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Callable

import streamlit as st
from PIL import Image, ImageOps

from src.Tools.utils.types import Tool6Context


# =============================================================================
# Public API (used by Step4 + Step10)
# =============================================================================
SS_COVER_BYTES = "tool6_cover_bytes"
SS_COVER_URL = "tool6_cover_url"

SS_PHOTO_BYTES = "photo_bytes"          # shared cache: {url: bytes}
SS_PHOTO_THUMBS = "photo_thumbs"        # shared thumbs cache: {url: jpg_bytes}

# Cover-local UI state
SS_COVER_PICK_LOCKED = "tool6_cover_pick_locked"
SS_COVER_PICK_SEARCH = "tool6_cover_pick_search"
SS_COVER_PICK_PAGE = "tool6_cover_pick_page"
SS_COVER_THUMBS = "tool6_cover_thumbs"      # local thumbs cache
SS_COVER_UPLOAD_BYTES = "cover_upload_bytes"

SS_COVER_OVERRIDES = "cover_table_overrides"
SS_COVER_DATE_FMT = "cover_date_format"

# Image fetch cache (TTL)
SS_IMG_CACHE = "tool6_cover_img_cache"      # {url: {"ts": float, "ok": bool, "bytes": b, "msg": str}}
SS_IMG_CACHE_CFG = "tool6_cover_img_cache_cfg"

# Widget keys
W_DATE_FMT_LABEL = "t6_date_fmt_label"
W_EDIT_TOGGLE = "t6_cover_edit_toggle"
W_SEARCH = "t6_cover_search"
W_PAGE = "t6_cover_page"
W_UPLOAD = "t6_cover_upload"


# =============================================================================
# UI constants
# =============================================================================
GRID_COLS = 2               # ✅ ثابت: دو ستون کنار هم
PER_PAGE = 12               # ✅ برای سرعت در Cloud پایین نگه دارید
THUMB_BOX = 200             # ✅ کمی کوچک‌تر از قبل (220) برای نمایش خردتر

# Hover HD tuning (performance)
HOVER_HD_MAXPX = 1600       # کمی کمتر => سریع‌تر
HOVER_HD_QUALITY = 85

# Cache / limits
IMG_TTL_OK = 20 * 60
IMG_TTL_FAIL = 90
IMG_CACHE_MAX_ITEMS = 600
IMG_MAX_MB = 25

# Adaptive HD budget (per visible page) - برای سرعت Cloud بهتره کم باشه
HD_BUDGET = 24


# =============================================================================
# Cover fields / defaults
# =============================================================================
DEFAULT_PREPARED_BY = "Premium Performance Consulting (PPC) & Act for Performance"
DEFAULT_PREPARED_FOR = "UNICEF"

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


# =============================================================================
# URL filtering
# =============================================================================
IMG_EXT_PATTERN = re.compile(r"\.(jpe?g|png|webp|gif|bmp|tiff?)(\?|#|$)", re.IGNORECASE)
AUDIO_EXT_PATTERN = re.compile(r"\.(mp3|wav|m4a|aac|ogg|opus|flac)(\?|#|$)", re.IGNORECASE)
NON_IMG_HINT = re.compile(r"\.(pdf|docx?|xlsx?|csv|zip|rar)(\?|#|$)", re.IGNORECASE)


# =============================================================================
# Helpers
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    return hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()[:12]


def _is_likely_image(url: str, label: str = "") -> bool:
    u = _s(url).lower()
    if not u:
        return False
    if NON_IMG_HINT.search(u) or AUDIO_EXT_PATTERN.search(u):
        return False
    if IMG_EXT_PATTERN.search(u):
        return True
    if "googleusercontent.com" in u or "lh3.googleusercontent.com" in u:
        return True
    lbl = _s(label).lower()
    if any(w in lbl for w in ("photo", "image", "picture")):
        return True
    return False


def _only_images(urls: List[str], labels: Dict[str, str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for u in urls or []:
        u = _s(u)
        if not u:
            continue
        if not _is_likely_image(u, labels.get(u, "")):
            continue
        if u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


# =============================================================================
# CSS (2-column + square cards + hover HD)
# =============================================================================
def _inject_css() -> None:
    st.markdown(
        f"""
<style>
  [data-testid="stVerticalBlock"] {{ gap: 0.65rem; }}

  .t6-card {{
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 14px;
    overflow: hidden;
    background: rgba(255,255,255,0.02);
  }}

  /* ✅ مربع واقعی */
  .t6-imgbox {{
    width: 100%;
    aspect-ratio: 1 / 1;
    background: rgba(0,0,0,0.08);
    display: grid;
    place-items: center;
    position: relative;
    overflow: hidden;
  }}

  .t6-imgbox img.t6-thumb {{
    width: 100%;
    height: 100%;
    object-fit: contain;
    display:block;
    transition: transform 160ms ease, opacity 120ms ease;
    transform: scale(1.0);
    opacity: 1;
  }}

  .t6-imgbox img.t6-hd {{
    position:absolute;
    inset:0;
    width: 100%;
    height: 100%;
    object-fit: contain;
    opacity:0;
    transform: scale(1.04);
    transition: opacity 120ms ease, transform 160ms ease;
    will-change: transform, opacity;
  }}

  .t6-card:hover .t6-imgbox img.t6-thumb {{
    transform: scale(1.08);
    opacity: 0.08;
  }}

  .t6-card:hover .t6-imgbox img.t6-hd {{
    opacity: 1;
    transform: scale(1.14);
  }}

  .t6-cap {{
    padding: 6px 10px 8px 10px;
    font-size: 11px;
    opacity: .86;
    line-height: 1.25;
    min-height: 34px;    /* ✅ هم‌تراز شدن کپشن‌ها */
    word-break: break-word;
    text-align: right;
  }}

  .t6-btn-wrap {{
    margin-top: 8px;
  }}

  .t6-box {{
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px;
    padding: 14px;
    background: rgba(255,255,255,0.02);
    margin: 0.25rem 0 0.75rem 0;
  }}
</style>
""",
        unsafe_allow_html=True,
    )


# =============================================================================
# Image processing
# =============================================================================
def _to_clean_png_bytes(raw: bytes, *, max_px: int = 2600) -> bytes:
    img = Image.open(BytesIO(raw))
    img = ImageOps.exif_transpose(img)

    w, h = img.size
    m = max(w, h)
    if m > max_px:
        scale = max_px / float(m)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")

    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _make_thumb_contain(img_bytes: bytes, *, box: int = THUMB_BOX, quality: int = 82) -> Optional[bytes]:
    """
    thumb سبک و سریع: مربع contain + پس‌زمینه ثابت
    """
    try:
        img = Image.open(BytesIO(img_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((box, box), Image.Resampling.LANCZOS)

        bg = Image.new("RGB", (box, box), (32, 32, 36))
        w, h = img.size
        bg.paste(img, ((box - w) // 2, (box - h) // 2))

        out = BytesIO()
        bg.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _make_hover_hd(img_bytes: bytes, *, max_px: int = HOVER_HD_MAXPX, quality: int = HOVER_HD_QUALITY) -> Optional[bytes]:
    try:
        img = Image.open(BytesIO(img_bytes))
        img = ImageOps.exif_transpose(img).convert("RGB")
        w, h = img.size
        m = max(w, h)
        if m > max_px:
            scale = max_px / float(m)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
        out = BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return None


@st.cache_data(show_spinner=False, max_entries=8192)
def _b64_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def _card_html_with_hover(thumb_bytes: Optional[bytes], hd_bytes: Optional[bytes], caption: str) -> str:
    cap = _s(caption)
    if not thumb_bytes:
        return f"<div class='t6-card'><div class='t6-imgbox'></div><div class='t6-cap'>{cap}</div></div>"

    b64t = _b64_bytes(thumb_bytes)
    thumb_tag = f"<img class='t6-thumb' loading='lazy' src='data:image/jpeg;base64,{b64t}'/>"

    hd_tag = ""
    if hd_bytes:
        b64h = _b64_bytes(hd_bytes)
        hd_tag = f"<img class='t6-hd' loading='lazy' src='data:image/jpeg;base64,{b64h}'/>"

    return (
        "<div class='t6-card'>"
        f"  <div class='t6-imgbox'>{thumb_tag}{hd_tag}</div>"
        f"  <div class='t6-cap'>{cap}</div>"
        "</div>"
    )


# =============================================================================
# TTL fetch cache wrapper (critical for Streamlit Cloud speed)
# =============================================================================
def _fetch_image_cached(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> Tuple[bool, Optional[bytes], str]:
    url = _s(url)
    if not url:
        return False, None, "Empty URL"

    ss = st.session_state
    cache: Dict[str, Dict[str, Any]] = ss.get(SS_IMG_CACHE, {}) or {}
    cfg = ss.get(
        SS_IMG_CACHE_CFG,
        {"ttl_ok": IMG_TTL_OK, "ttl_fail": IMG_TTL_FAIL, "max_items": IMG_CACHE_MAX_ITEMS, "max_mb": IMG_MAX_MB},
    )

    ttl_ok = int(cfg.get("ttl_ok", IMG_TTL_OK))
    ttl_fail = int(cfg.get("ttl_fail", IMG_TTL_FAIL))
    max_items = int(cfg.get("max_items", IMG_CACHE_MAX_ITEMS))
    max_mb = int(cfg.get("max_mb", IMG_MAX_MB))

    now = time.time()
    hit = cache.get(url)
    if isinstance(hit, dict):
        ts = float(hit.get("ts") or 0.0)
        ok = bool(hit.get("ok"))
        age = now - ts
        if ok and age < ttl_ok:
            b = hit.get("bytes")
            return True, (bytes(b) if isinstance(b, (bytes, bytearray)) else None), _s(hit.get("msg") or "OK")
        if (not ok) and age < ttl_fail:
            return False, None, _s(hit.get("msg") or "Recently failed")

    # LRU-ish trim
    if len(cache) > max_items:
        items = sorted(cache.items(), key=lambda kv: float((kv[1] or {}).get("ts") or 0.0))
        drop_n = max(1, int(len(items) * 0.25))
        for k, _ in items[:drop_n]:
            cache.pop(k, None)

    ok, b, msg = fetch_image(url)
    if ok and b:
        if len(b) > max_mb * 1024 * 1024:
            cache[url] = {"ts": now, "ok": False, "bytes": None, "msg": f"Image too large (> {max_mb}MB)"}
            ss[SS_IMG_CACHE] = cache
            return False, None, f"Image too large (> {max_mb}MB)"
        cache[url] = {"ts": now, "ok": True, "bytes": b, "msg": "OK"}
        ss[SS_IMG_CACHE] = cache
        return True, b, "OK"

    cache[url] = {"ts": now, "ok": False, "bytes": None, "msg": _s(msg) or "Fetch failed"}
    ss[SS_IMG_CACHE] = cache
    return False, None, _s(msg) or "Fetch failed"


def ensure_full_image_bytes(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    url = _s(url)
    if not url:
        return
    pb: Dict[str, bytes] = st.session_state.get(SS_PHOTO_BYTES, {}) or {}
    if url in pb and pb[url]:
        return

    ok, b, _ = _fetch_image_cached(url, fetch_image=fetch_image)
    if ok and b:
        pb[url] = b
        st.session_state[SS_PHOTO_BYTES] = pb


def cache_thumbnail_only(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    url = _s(url)
    if not url:
        return

    ss = st.session_state
    thumbs_local: Dict[str, bytes] = ss.get(SS_COVER_THUMBS, {}) or {}
    thumbs_global: Dict[str, bytes] = ss.get(SS_PHOTO_THUMBS, {}) or {}

    if (url in thumbs_local and thumbs_local[url]) or (url in thumbs_global and thumbs_global[url]):
        if url not in thumbs_local and url in thumbs_global:
            thumbs_local[url] = thumbs_global[url]
            ss[SS_COVER_THUMBS] = thumbs_local
        return

    pb: Dict[str, bytes] = ss.get(SS_PHOTO_BYTES, {}) or {}
    src = pb.get(url)

    if not src:
        ok, b, _ = _fetch_image_cached(url, fetch_image=fetch_image)
        if not (ok and b):
            return
        src = b

    th = _make_thumb_contain(src, box=THUMB_BOX, quality=82)
    if th:
        thumbs_local[url] = th
        thumbs_global[url] = th
        ss[SS_COVER_THUMBS] = thumbs_local
        ss[SS_PHOTO_THUMBS] = thumbs_global


def _thumb_and_optional_hd(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
    want_hd: bool,
) -> Tuple[Optional[bytes], Optional[bytes]]:
    ss = st.session_state
    tb = (ss.get(SS_COVER_THUMBS, {}) or {}).get(url) or (ss.get(SS_PHOTO_THUMBS, {}) or {}).get(url)

    if not tb:
        cache_thumbnail_only(url, fetch_image=fetch_image)
        tb = (ss.get(SS_COVER_THUMBS, {}) or {}).get(url) or (ss.get(SS_PHOTO_THUMBS, {}) or {}).get(url)

    hd = None
    if want_hd:
        pb: Dict[str, bytes] = ss.get(SS_PHOTO_BYTES, {}) or {}
        src = pb.get(url)
        if not src:
            ok, b, _ = _fetch_image_cached(url, fetch_image=fetch_image)
            if ok and b:
                src = b
        if src:
            hd = _make_hover_hd(src)

    return tb, hd


# =============================================================================
# Date formatting
# =============================================================================
def _parse_iso_like_date(value: Any) -> Optional[datetime]:
    text = _s(value)
    if not text:
        return None
    text = text.split(".")[0].replace("T", " ").replace("Z", "").strip()
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _format_visit_date(raw_date: Any, date_format: str) -> str:
    dt = _parse_iso_like_date(raw_date)
    if not dt:
        text = _s(raw_date)
        return text.split(" ")[0] if " " in text else text
    try:
        return dt.strftime(date_format)
    except ValueError:
        return dt.strftime("%d/%b/%Y")


# =============================================================================
# Cover defaults
# =============================================================================
def _build_cover_defaults(ctx: Tool6Context) -> Dict[str, str]:
    row = getattr(ctx, "row", {}) or {}
    defaults = getattr(ctx, "defaults", {}) or {}

    province = _s(defaults.get("Province", "")) or _s(row.get("A01_Province"))
    district = _s(defaults.get("District", "")) or _s(row.get("A02_District"))
    village = _s(defaults.get("Village / Community", "")) or _s(row.get("Village"))
    location = ", ".join([x for x in (province, district, village) if x])

    project_title = _s(row.get("Activity_Name") or defaults.get("Project Name") or defaults.get("Project Title") or "")
    visit_no = _s(row.get("A26_Visit_number") or defaults.get("Visit No") or defaults.get("Visit No.") or "1")

    intervention = _s(
        row.get("Tools_Name")
        or row.get("Tools")
        or defaults.get("Tools Name")
        or defaults.get("Type of Intervention")
        or "Solar Water Supply"
    )

    start_time = row.get("starttime") or defaults.get("Date of Visit") or ""
    fmt = _s(st.session_state.get(SS_COVER_DATE_FMT, "%d/%b/%Y")) or "%d/%b/%Y"
    visit_date = _format_visit_date(start_time, fmt) if start_time else ""

    partner = _s(row.get("Primary_Partner_Name") or defaults.get("Name of the IP, Organization / NGO") or "")

    return {
        "Project Title": project_title,
        "Visit No.": visit_no,
        "Type of Intervention": intervention,
        "Province / District / Village": location,
        "Date of Visit": visit_date,
        "Implementing Partner (IP)": partner,
        "Prepared by": DEFAULT_PREPARED_BY,
        "Prepared for": DEFAULT_PREPARED_FOR,
    }


# =============================================================================
# Public API helpers
# =============================================================================
def resolve_cover_bytes() -> Optional[bytes]:
    b = st.session_state.get(SS_COVER_BYTES)
    if isinstance(b, (bytes, bytearray)) and b:
        return bytes(b)

    for k in ("cover_bytes", SS_COVER_UPLOAD_BYTES):
        bb = st.session_state.get(k)
        if isinstance(bb, (bytes, bytearray)) and bb:
            return bytes(bb)

    pb = st.session_state.get(SS_PHOTO_BYTES)
    cu = st.session_state.get(SS_COVER_URL)
    if isinstance(pb, dict) and cu and cu in pb and pb[cu]:
        if isinstance(pb[cu], (bytes, bytearray)):
            return bytes(pb[cu])

    return None


# =============================================================================
# HARD hide/cleanup: keep only cover
# =============================================================================
def _keep_only_cover(*, cover_url: str, cover_bytes: Optional[bytes]) -> None:
    ss = st.session_state
    cover_url = _s(cover_url)

    ss[SS_COVER_URL] = cover_url
    if cover_bytes:
        ss[SS_COVER_BYTES] = bytes(cover_bytes)
        ss["cover_bytes"] = bytes(cover_bytes)

    tl = ss.get(SS_COVER_THUMBS) or {}
    ss[SS_COVER_THUMBS] = {cover_url: tl[cover_url]} if isinstance(tl, dict) and cover_url in tl else {}

    tg = ss.get(SS_PHOTO_THUMBS) or {}
    ss[SS_PHOTO_THUMBS] = {cover_url: tg[cover_url]} if isinstance(tg, dict) and cover_url in tg else {}

    pb = ss.get(SS_PHOTO_BYTES) or {}
    ss[SS_PHOTO_BYTES] = {cover_url: pb[cover_url]} if isinstance(pb, dict) and cover_url in pb else {}

    imgc = ss.get(SS_IMG_CACHE) or {}
    ss[SS_IMG_CACHE] = {cover_url: imgc[cover_url]} if isinstance(imgc, dict) and cover_url in imgc else {}


# =============================================================================
# State init
# =============================================================================
def _ensure_state(ctx: Tool6Context) -> None:
    ss = st.session_state
    ss.setdefault(SS_COVER_DATE_FMT, "%d/%b/%Y")

    if SS_COVER_OVERRIDES not in ss or not isinstance(ss[SS_COVER_OVERRIDES], dict):
        ss[SS_COVER_OVERRIDES] = _build_cover_defaults(ctx)
    else:
        fresh = _build_cover_defaults(ctx)
        cur = ss[SS_COVER_OVERRIDES]
        for k, v in fresh.items():
            cur.setdefault(k, v)
        ss[SS_COVER_OVERRIDES] = cur

    ss.setdefault(SS_COVER_PICK_LOCKED, False)
    ss.setdefault(SS_COVER_PICK_SEARCH, "")
    ss.setdefault(SS_COVER_PICK_PAGE, 1)

    ss.setdefault(SS_COVER_THUMBS, {})
    if not isinstance(ss[SS_COVER_THUMBS], dict):
        ss[SS_COVER_THUMBS] = {}

    ss.setdefault(SS_PHOTO_BYTES, {})
    if not isinstance(ss[SS_PHOTO_BYTES], dict):
        ss[SS_PHOTO_BYTES] = {}

    ss.setdefault(SS_PHOTO_THUMBS, {})
    if not isinstance(ss[SS_PHOTO_THUMBS], dict):
        ss[SS_PHOTO_THUMBS] = {}

    ss.setdefault(SS_COVER_UPLOAD_BYTES, None)

    ss.setdefault(SS_IMG_CACHE, {})
    if not isinstance(ss[SS_IMG_CACHE], dict):
        ss[SS_IMG_CACHE] = {}

    ss.setdefault(
        SS_IMG_CACHE_CFG,
        {"ttl_ok": IMG_TTL_OK, "ttl_fail": IMG_TTL_FAIL, "max_items": IMG_CACHE_MAX_ITEMS, "max_mb": IMG_MAX_MB},
    )


# =============================================================================
# Instant cover-table save (no form submit)
# =============================================================================
def _set_cover_field(field: str, widget_key: str) -> None:
    ss = st.session_state
    table = ss.get(SS_COVER_OVERRIDES, {}) or {}
    if not isinstance(table, dict):
        table = {}
    table[field] = _s(ss.get(widget_key))
    ss[SS_COVER_OVERRIDES] = table


def _apply_date_format_from_ctx(ctx: Tool6Context) -> None:
    ss = st.session_state
    fmt = _s(ss.get(SS_COVER_DATE_FMT, "%d/%b/%Y")) or "%d/%b/%Y"
    row = getattr(ctx, "row", {}) or {}
    start_time = row.get("starttime")
    if not start_time:
        return

    table = ss.get(SS_COVER_OVERRIDES, {}) or {}
    if not isinstance(table, dict):
        table = {}

    table["Date of Visit"] = _format_visit_date(start_time, fmt)
    ss[SS_COVER_OVERRIDES] = table


def _on_date_fmt_change(ctx: Tool6Context) -> None:
    ss = st.session_state
    fmt_map = dict(DATE_FORMATS)
    picked_label = _s(ss.get(W_DATE_FMT_LABEL))
    if picked_label and picked_label in fmt_map:
        ss[SS_COVER_DATE_FMT] = fmt_map[picked_label]
    _apply_date_format_from_ctx(ctx)


# =============================================================================
# Picker (FAST + EXACT 2-up layout like your screenshot)
# =============================================================================
def _render_picker(
    *,
    urls: List[str],
    labels: Dict[str, str],
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    ss = st.session_state
    locked = bool(ss.get(SS_COVER_PICK_LOCKED, False))
    cover_url = _s(ss.get(SS_COVER_URL))

    def lab(u: str) -> str:
        return _s(labels.get(u, u))

    # Locked => show ONLY cover
    if locked and (cover_url or resolve_cover_bytes()):
        st.markdown("<div class='t6-box'>", unsafe_allow_html=True)
        st.markdown("**Selected Cover (only this image is kept)**")

        if not cover_url and resolve_cover_bytes():
            st.image(resolve_cover_bytes(), use_container_width=True)
        else:
            cache_thumbnail_only(cover_url, fetch_image=fetch_image)
            tb = (ss.get(SS_COVER_THUMBS, {}) or {}).get(cover_url) or (ss.get(SS_PHOTO_THUMBS, {}) or {}).get(cover_url)
            if tb:
                ensure_full_image_bytes(cover_url, fetch_image=fetch_image)
                src = (ss.get(SS_PHOTO_BYTES, {}) or {}).get(cover_url)
                hd = _make_hover_hd(src) if src else None
                st.markdown(_card_html_with_hover(tb, hd, lab(cover_url)), unsafe_allow_html=True)
            else:
                st.write(lab(cover_url))

        c1, c2 = st.columns([1, 1], gap="small")
        with c1:
            if st.button("Change cover", use_container_width=True, key=_key("chg_cover")):
                ss[SS_COVER_PICK_LOCKED] = False
                ss[SS_COVER_URL] = ""
                ss[SS_COVER_BYTES] = None
                ss[SS_COVER_UPLOAD_BYTES] = None
                ss[SS_COVER_THUMBS] = {}
                ss[SS_PHOTO_THUMBS] = {}
                ss[SS_PHOTO_BYTES] = {}
                ss[SS_IMG_CACHE] = {}
                st.rerun()
        with c2:
            if st.button("Clear cover", use_container_width=True, key=_key("clr_cover")):
                ss[SS_COVER_PICK_LOCKED] = False
                ss[SS_COVER_URL] = ""
                ss[SS_COVER_BYTES] = None
                ss[SS_COVER_UPLOAD_BYTES] = None
                ss[SS_COVER_THUMBS] = {}
                ss[SS_PHOTO_THUMBS] = {}
                ss[SS_PHOTO_BYTES] = {}
                ss[SS_IMG_CACHE] = {}
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Not locked => show gallery
    q = st.text_input(
        "Search photos",
        value=_s(ss.get(SS_COVER_PICK_SEARCH, "")),
        placeholder="Search by name…",
        label_visibility="collapsed",
        key=W_SEARCH,
    ).strip().lower()
    ss[SS_COVER_PICK_SEARCH] = q

    filtered = [u for u in urls if (q in lab(u).lower())] if q else list(urls)
    if not filtered:
        st.info("No photos match your search.")
        return

    total = len(filtered)
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    p1, p2, p3 = st.columns([0.40, 0.30, 0.30], gap="small")
    with p1:
        page = st.number_input(
            "Page",
            min_value=1,
            max_value=pages,
            value=int(ss.get(SS_COVER_PICK_PAGE, 1) or 1),
            step=1,
            label_visibility="collapsed",
            key=W_PAGE,
        )
        ss[SS_COVER_PICK_PAGE] = int(page)
    with p2:
        st.caption(f"{total} photos")
    with p3:
        if st.button("Clear search", use_container_width=True, key=_key("clear_search")):
            ss[SS_COVER_PICK_SEARCH] = ""
            ss[SS_COVER_PICK_PAGE] = 1
            st.rerun()

    start = (int(page) - 1) * PER_PAGE
    chunk = filtered[start : start + PER_PAGE]

    # ✅ preload thumbs only for visible page (fast)
    for u in chunk:
        cache_thumbnail_only(u, fetch_image=fetch_image)

    # ✅ HD only for first N visible items
    hd_set = set(chunk[: min(HD_BUDGET, len(chunk))])

    # ✅ EXACT 2-up layout like screenshot: use st.columns(2)
    for i in range(0, len(chunk), GRID_COLS):
        row = chunk[i : i + GRID_COLS]
        cols = st.columns(GRID_COLS, gap="medium")

        for col, u in zip(cols, row):
            with col:
                tb, hd = _thumb_and_optional_hd(u, fetch_image=fetch_image, want_hd=(u in hd_set))
                st.markdown(_card_html_with_hover(tb, hd, lab(u)), unsafe_allow_html=True)

                st.markdown("<div class='t6-btn-wrap'>", unsafe_allow_html=True)
                if st.button("Select", use_container_width=True, key=_key("sel", u)):
                    ensure_full_image_bytes(u, fetch_image=fetch_image)
                    b = (ss.get(SS_PHOTO_BYTES, {}) or {}).get(u)

                    ss[SS_COVER_UPLOAD_BYTES] = None
                    ss[SS_COVER_PICK_LOCKED] = True

                    _keep_only_cover(cover_url=u, cover_bytes=b)
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# Panels (fragmented so form edits don't rerender heavy gallery)
# =============================================================================
@st.fragment
def _images_panel(ctx: Tool6Context, fetch_image) -> None:
    st.markdown("### Available Images")
    all_urls = getattr(ctx, "all_photo_urls", []) or []
    labels = getattr(ctx, "photo_label_by_url", {}) or {}
    imgs = _only_images(all_urls, labels)

    if not imgs and not resolve_cover_bytes():
        st.warning("No suitable images found for this report.")
    else:
        _render_picker(urls=imgs, labels=labels, fetch_image=fetch_image)


@st.fragment
def _upload_panel() -> None:
    st.markdown("### Upload Custom Image")
    file = st.file_uploader(
        "Choose file",
        type=["jpg", "jpeg", "png"],
        label_visibility="collapsed",
        key=W_UPLOAD,
    )
    if file:
        raw = file.read()
        try:
            processed = _to_clean_png_bytes(raw)
        except Exception:
            processed = raw

        ss = st.session_state
        ss[SS_COVER_UPLOAD_BYTES] = processed
        ss[SS_COVER_BYTES] = processed
        ss["cover_bytes"] = processed
        ss[SS_COVER_URL] = ""
        ss[SS_COVER_PICK_LOCKED] = True

        # keep only uploaded cover
        ss[SS_COVER_THUMBS] = {}
        ss[SS_PHOTO_THUMBS] = {}
        ss[SS_PHOTO_BYTES] = {}
        ss[SS_IMG_CACHE] = {}

        st.image(processed, use_container_width=True, caption="Uploaded cover")
        st.success("Custom cover uploaded and selected.")
        st.rerun()


# =============================================================================
# Main render
# =============================================================================
def render_step(
    ctx: Tool6Context,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> bool:
    """
    Step 1 (FAST):
      - ✅ 2 ستون دقیقاً مثل اسکرین‌شات
      - ✅ کارت مربع واقعی
      - ✅ TTL fetch cache
      - ✅ فقط thumbهای صفحه فعلی
      - ✅ HD محدود برای سرعت
      - ✅ st.fragment برای جلوگیری از rerun سنگین
    """
    _ensure_state(ctx)
    _inject_css()

    left, right = st.columns([4, 4], gap="large")
    with left:
        _images_panel(ctx, fetch_image)
    with right:
        _upload_panel()

    st.divider()
    st.subheader("Cover Page Details")

    # --- Date format ---
    fmt_labels = [x for x, _ in DATE_FORMATS]
    cur_fmt = _s(st.session_state.get(SS_COVER_DATE_FMT, "%d/%b/%Y")) or "%d/%b/%Y"
    idx = next((i for i, (_, f) in enumerate(DATE_FORMATS) if f == cur_fmt), 0)

    if W_DATE_FMT_LABEL not in st.session_state:
        st.session_state[W_DATE_FMT_LABEL] = fmt_labels[idx]

    st.selectbox(
        "Date of Visit format",
        fmt_labels,
        index=fmt_labels.index(st.session_state[W_DATE_FMT_LABEL])
        if st.session_state[W_DATE_FMT_LABEL] in fmt_labels
        else idx,
        key=W_DATE_FMT_LABEL,
        on_change=_on_date_fmt_change,
        kwargs={"ctx": ctx},
    )
    _apply_date_format_from_ctx(ctx)

    cover_table: Dict[str, str] = st.session_state.get(SS_COVER_OVERRIDES, {}) or {}

    edit = st.toggle("Edit cover details", value=bool(st.session_state.get(W_EDIT_TOGGLE, False)), key=W_EDIT_TOGGLE)

    if not edit:
        st.markdown("<div class='t6-box'>", unsafe_allow_html=True)
        for label, field in COVER_FIELDS:
            val = _s(cover_table.get(field))
            st.markdown(f"**{label}** {val or '—'}")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        a, b = st.columns(2, gap="large")

        def inp_text(field: str, value: str) -> None:
            k = _key("f", field)
            st.text_input(
                field,
                value=value,
                key=k,
                on_change=_set_cover_field,
                kwargs={"field": field, "widget_key": k},
            )

        def inp_area(field: str, value: str, h: int = 80) -> None:
            k = _key("f", field)
            st.text_area(
                field,
                value=value,
                height=h,
                key=k,
                on_change=_set_cover_field,
                kwargs={"field": field, "widget_key": k},
            )

        with a:
            inp_area("Project Title", _s(cover_table.get("Project Title")), 80)
            inp_text("Visit No.", _s(cover_table.get("Visit No.")))
            inp_text("Type of Intervention", _s(cover_table.get("Type of Intervention")))
            inp_text("Date of Visit", _s(cover_table.get("Date of Visit")))

        with b:
            inp_area("Province / District / Village", _s(cover_table.get("Province / District / Village")), 80)
            inp_area("Implementing Partner (IP)", _s(cover_table.get("Implementing Partner (IP)")), 80)
            inp_text("Prepared by", _s(cover_table.get("Prepared by")) or DEFAULT_PREPARED_BY)
            inp_text("Prepared for", _s(cover_table.get("Prepared for")) or DEFAULT_PREPARED_FOR)

        st.caption("✅ Changes are saved instantly (no Save button needed).")

    return bool(resolve_cover_bytes())
