from __future__ import annotations

import base64
import hashlib
import re
from io import BytesIO
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Callable

import streamlit as st
from PIL import Image

from pages.Tool_6 import _to_clean_png_bytes
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
SS_COVER_THUMBS = "tool6_cover_thumbs"  # local thumbs cache (fast, small)
SS_COVER_UPLOAD_BYTES = "cover_upload_bytes"

SS_COVER_OVERRIDES = "cover_table_overrides"
SS_COVER_DATE_FMT = "cover_date_format"


def resolve_cover_bytes() -> Optional[bytes]:
    """
    ✅ Step10 calls this (or your wrapper calls it).
    Must return cover image bytes if available.
    """
    b = st.session_state.get(SS_COVER_BYTES)
    if isinstance(b, (bytes, bytearray)) and b:
        return bytes(b)

    # legacy fallbacks
    for k in ("cover_bytes", SS_COVER_UPLOAD_BYTES):
        bb = st.session_state.get(k)
        if isinstance(bb, (bytes, bytearray)) and bb:
            return bytes(bb)

    # fallback: if cover url exists in photo_bytes dict
    pb = st.session_state.get(SS_PHOTO_BYTES)
    cu = st.session_state.get(SS_COVER_URL)
    if isinstance(pb, dict) and cu and cu in pb and pb[cu]:
        if isinstance(pb[cu], (bytes, bytearray)):
            return bytes(pb[cu])

    return None


def ensure_full_image_bytes(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    """
    ✅ Compatibility with Step4 imports.
    Caches FULL bytes in st.session_state["photo_bytes"].
    """
    url = _s(url)
    if not url:
        return
    pb: Dict[str, bytes] = st.session_state.get(SS_PHOTO_BYTES, {}) or {}
    if url in pb and pb[url]:
        return
    ok, b, _ = fetch_image(url)
    if ok and b:
        pb[url] = b
        st.session_state[SS_PHOTO_BYTES] = pb


def cache_thumbnail_only(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    """
    ✅ Compatibility with Step4 imports.
    Stores thumbs into BOTH:
      - cover-local: tool6_cover_thumbs (fast Step1)
      - global: photo_thumbs (so Step4 can reuse)
    """
    url = _s(url)
    if not url:
        return

    thumbs_local: Dict[str, bytes] = st.session_state.get(SS_COVER_THUMBS, {}) or {}
    thumbs_global: Dict[str, bytes] = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}

    if (url in thumbs_local and thumbs_local[url]) or (url in thumbs_global and thumbs_global[url]):
        # sync local from global if needed
        if url not in thumbs_local and url in thumbs_global:
            thumbs_local[url] = thumbs_global[url]
            st.session_state[SS_COVER_THUMBS] = thumbs_local
        return

    ok, b, _ = fetch_image(url)
    if ok and b:
        th = _make_thumb_contain(b, box=THUMB_BOX, quality=82)
        if th:
            thumbs_local[url] = th
            thumbs_global[url] = th
            st.session_state[SS_COVER_THUMBS] = thumbs_local
            st.session_state[SS_PHOTO_THUMBS] = thumbs_global


def render_thumbnail(thumb_bytes: bytes, caption: str) -> None:
    """
    ✅ Compatibility with Step4 imports.
    Renders a square card with 'contain' (no crop).
    """
    if not thumb_bytes:
        st.caption("Preview not available")
        if caption:
            st.caption(_s(caption))
        return

    b64 = base64.b64encode(thumb_bytes).decode("utf-8")
    cap = _s(caption)
    st.markdown(
        f"""
<div class="t6-thumb-card">
  <img src="data:image/jpeg;base64,{b64}" />
  <div class="t6-thumb-cap">{cap}</div>
</div>
""",
        unsafe_allow_html=True,
    )


# =============================================================================
# UI constants
# =============================================================================
GRID_COLS = 3
PER_PAGE = 12
THUMB_BOX = 220  # square card size


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


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    return hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()[:10]


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
# Thumb (square contain, no crop)
# =============================================================================
def _make_thumb_contain(img_bytes: bytes, *, box: int, quality: int) -> Optional[bytes]:
    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((box, box), Image.Resampling.LANCZOS)

        bg = Image.new("RGB", (box, box), (32, 32, 36))
        w, h = img.size
        bg.paste(img, ((box - w) // 2, (box - h) // 2))

        out = BytesIO()
        bg.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _inject_css() -> None:
    st.markdown(
        f"""
<style>
  [data-testid="stVerticalBlock"] {{ gap: 0.70rem; }}

  .t6-grid {{
    display:grid;
    grid-template-columns: repeat({GRID_COLS}, minmax(0, 1fr));
    gap: 12px;
    align-items: start;
  }}

  .t6-thumb-card {{
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 14px;
    overflow: hidden;
    background: rgba(255,255,255,0.02);
  }}

  .t6-thumb-card img {{
    width: 100%;
    height: {THUMB_BOX}px;
    object-fit: contain;             /* ✅ full image */
    background: rgba(0,0,0,0.10);
    display:block;
  }}

  .t6-thumb-cap {{
    padding: 8px 10px 10px 10px;
    font-size: 12px;
    opacity: .86;
    line-height: 1.25;
    min-height: 40px;
    word-break: break-word;
  }}

  .t6-btn-row {{
    display:flex;
    gap: 10px;                       /* ✅ spacing between buttons */
    margin-top: 10px;
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
# Cover defaults
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
# HARD hide/cleanup: keep only cover
# =============================================================================
def _keep_only_cover(*, cover_url: str, cover_bytes: Optional[bytes]) -> None:
    """
    ✅ After selecting cover:
      - show ONLY that image (others hide)
      - keep caches ONLY for cover (speed)
    """
    ss = st.session_state

    ss[SS_COVER_URL] = _s(cover_url)
    if cover_bytes:
        ss[SS_COVER_BYTES] = bytes(cover_bytes)
        ss["cover_bytes"] = bytes(cover_bytes)  # legacy compatible
    else:
        ss[SS_COVER_BYTES] = ss.get(SS_COVER_BYTES)

    # thumbs: keep only cover
    tl = ss.get(SS_COVER_THUMBS) or {}
    if isinstance(tl, dict) and cover_url in tl:
        ss[SS_COVER_THUMBS] = {cover_url: tl[cover_url]}
    else:
        ss[SS_COVER_THUMBS] = {}

    tg = ss.get(SS_PHOTO_THUMBS) or {}
    if isinstance(tg, dict) and cover_url in tg:
        ss[SS_PHOTO_THUMBS] = {cover_url: tg[cover_url]}
    else:
        ss[SS_PHOTO_THUMBS] = {}

    # full bytes: keep only cover
    pb = ss.get(SS_PHOTO_BYTES) or {}
    if isinstance(pb, dict) and cover_url and cover_url in pb:
        ss[SS_PHOTO_BYTES] = {cover_url: pb[cover_url]}
    else:
        ss[SS_PHOTO_BYTES] = {}

    # remove any other selections/maps if you had them (safe)
    # (we don't require them for cover)
    # you can add more cleanup keys if your project has more caches.


# =============================================================================
# State init
# =============================================================================
def _ensure_state(ctx: Tool6Context) -> None:
    ss = st.session_state
    ss.setdefault(SS_COVER_DATE_FMT, "%d/%b/%Y")

    if SS_COVER_OVERRIDES not in ss or not isinstance(ss[SS_COVER_OVERRIDES], dict):
        ss[SS_COVER_OVERRIDES] = _build_cover_defaults(ctx)
    else:
        # don't overwrite user edits; only set missing keys
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


# =============================================================================
# Picker (independent)
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

    # If locked -> show ONLY cover, hide all else
    if locked and (cover_url or resolve_cover_bytes()):
        st.markdown("<div class='t6-box'>", unsafe_allow_html=True)
        st.markdown("**Selected Cover (only this image is kept)**")

        # If cover was uploaded (no URL)
        if not cover_url and resolve_cover_bytes():
            st.image(resolve_cover_bytes(), use_container_width=True)
        else:
            cache_thumbnail_only(cover_url, fetch_image=fetch_image)
            tb = (ss.get(SS_COVER_THUMBS, {}) or {}).get(cover_url) or (ss.get(SS_PHOTO_THUMBS, {}) or {}).get(cover_url)
            if tb:
                render_thumbnail(tb, lab(cover_url))
            else:
                st.write(lab(cover_url))

        c1, c2 = st.columns([1, 1], gap="small")
        with c1:
            if st.button("Change cover", use_container_width=True, key=_key("chg_cover")):
                ss[SS_COVER_PICK_LOCKED] = False
                ss[SS_COVER_URL] = ""
                ss[SS_COVER_BYTES] = None
                ss[SS_COVER_UPLOAD_BYTES] = None
                # do not keep caches
                ss[SS_COVER_THUMBS] = {}
                ss[SS_PHOTO_THUMBS] = {}
                ss[SS_PHOTO_BYTES] = {}
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
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Not locked => show gallery (fast)
    q = st.text_input(
        "Search photos",
        value=_s(ss.get(SS_COVER_PICK_SEARCH, "")),
        placeholder="Search by name…",
        label_visibility="collapsed",
        key=_key("search"),
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
            key=_key("page"),
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

    # preload thumbs only for visible page (FAST)
    for u in chunk:
        cache_thumbnail_only(u, fetch_image=fetch_image)

    thumbs = ss.get(SS_COVER_THUMBS, {}) or {}

    st.markdown("<div class='t6-grid'>", unsafe_allow_html=True)
    for u in chunk:
        tb = thumbs.get(u)
        cap = lab(u)

        st.markdown("<div>", unsafe_allow_html=True)
        if tb:
            st.markdown(_thumb_card_html(tb, cap), unsafe_allow_html=True)
        else:
            st.markdown(f"<div class='t6-thumb-card'><div class='t6-thumb-cap'>{cap}</div></div>", unsafe_allow_html=True)

        st.markdown("<div class='t6-btn-row'>", unsafe_allow_html=True)
        if st.button("Select as cover", use_container_width=True, key=_key("sel", u)):
            ensure_full_image_bytes(u, fetch_image=fetch_image)
            b = (ss.get(SS_PHOTO_BYTES, {}) or {}).get(u)

            ss[SS_COVER_UPLOAD_BYTES] = None
            ss[SS_COVER_PICK_LOCKED] = True

            _keep_only_cover(cover_url=u, cover_bytes=b)
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _thumb_card_html(thumb_bytes: bytes, caption: str) -> str:
    b64 = base64.b64encode(thumb_bytes).decode("utf-8")
    cap = _s(caption)
    return (
        "<div class='t6-thumb-card'>"
        f"<img src='data:image/jpeg;base64,{b64}'/>"
        f"<div class='t6-thumb-cap'>{cap}</div>"
        "</div>"
    )


# =============================================================================
# Main render
# =============================================================================
def render_step(ctx: Tool6Context, *, fetch_image) -> bool:
    """
    ✅ Independent Step 1:
      - user selects ONE cover
      - all other photos hide + caches cleaned for maximum speed
      - Step10 can call resolve_cover_bytes()
    """
    _ensure_state(ctx)
    _inject_css()

    ss = st.session_state
    cover_table: Dict[str, str] = ss.get(SS_COVER_OVERRIDES, {}) or {}

    left, right = st.columns([5, 4], gap="large")

    with left:
        st.markdown("### Available Images")
        all_urls = getattr(ctx, "all_photo_urls", []) or []
        labels = getattr(ctx, "photo_label_by_url", {}) or {}
        imgs = _only_images(all_urls, labels)

        if not imgs and not resolve_cover_bytes():
            st.warning("No suitable images found for this report.")
        else:
            _render_picker(urls=imgs, labels=labels, fetch_image=fetch_image)

    with right:
        st.markdown("### Upload Custom Image")
        file = st.file_uploader(
            "Choose file",
            type=["jpg", "jpeg", "png"],
            label_visibility="collapsed",
            key=_key("upload"),
        )
        if file:
            raw = file.read()
            try:
                processed = _to_clean_png_bytes(raw)
            except Exception:
                processed = raw

            ss[SS_COVER_UPLOAD_BYTES] = processed
            ss[SS_COVER_BYTES] = processed
            ss["cover_bytes"] = processed  # legacy
            ss[SS_COVER_URL] = ""
            ss[SS_COVER_PICK_LOCKED] = True

            # hide/clean everything else (keep only uploaded cover)
            ss[SS_COVER_THUMBS] = {}
            ss[SS_PHOTO_THUMBS] = {}
            ss[SS_PHOTO_BYTES] = {}
            st.image(processed, use_container_width=True, caption="Uploaded cover")
            st.success("Custom cover uploaded and selected.")
            st.rerun()

    st.divider()
    st.subheader("Cover Page Details")

    # Date format
    fmt_labels = [x for x, _ in DATE_FORMATS]
    fmt_map = dict(DATE_FORMATS)
    cur_fmt = _s(ss.get(SS_COVER_DATE_FMT, "%d/%b/%Y")) or "%d/%b/%Y"
    idx = next((i for i, (_, f) in enumerate(DATE_FORMATS) if f == cur_fmt), 0)

    chosen = st.selectbox("Date of Visit format", fmt_labels, index=idx, key=_key("date_fmt"))
    ss[SS_COVER_DATE_FMT] = fmt_map[chosen]

    if start_time := (getattr(ctx, "row", {}) or {}).get("starttime"):
        cover_table["Date of Visit"] = _format_visit_date(start_time, ss[SS_COVER_DATE_FMT])

    edit = st.toggle("Edit cover details", value=False, key=_key("edit"))

    if not edit:
        st.markdown("<div class='t6-box'>", unsafe_allow_html=True)
        for label, field in COVER_FIELDS:
            val = _s(cover_table.get(field))
            st.markdown(f"**{label}** {val or '—'}")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        with st.form("cover_form"):
            a, b = st.columns(2, gap="large")
            with a:
                cover_table["Project Title"] = st.text_area("Project Title", value=_s(cover_table.get("Project Title")), height=80)
                cover_table["Visit No."] = st.text_input("Visit No.", value=_s(cover_table.get("Visit No.")))
                cover_table["Type of Intervention"] = st.text_input("Type of Intervention", value=_s(cover_table.get("Type of Intervention")))
                cover_table["Date of Visit"] = st.text_input("Date of Visit", value=_s(cover_table.get("Date of Visit")))
            with b:
                cover_table["Province / District / Village"] = st.text_area("Province / District / Village", value=_s(cover_table.get("Province / District / Village")), height=80)
                cover_table["Implementing Partner (IP)"] = st.text_area("Implementing Partner (IP)", value=_s(cover_table.get("Implementing Partner (IP)")), height=80)
                cover_table["Prepared by"] = st.text_input("Prepared by", value=_s(cover_table.get("Prepared by")) or DEFAULT_PREPARED_BY)
                cover_table["Prepared for"] = st.text_input("Prepared for", value=_s(cover_table.get("Prepared for")) or DEFAULT_PREPARED_FOR)

            if st.form_submit_button("Save Changes", use_container_width=True):
                ss[SS_COVER_OVERRIDES] = dict(cover_table)
                st.success("Cover details saved.")
                st.rerun()

    # ✅ only true when cover exists
    return bool(resolve_cover_bytes())
