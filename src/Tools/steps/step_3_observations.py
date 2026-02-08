from __future__ import annotations

import base64
import csv
import hashlib
import re
import time
from io import BytesIO, StringIO
from typing import Any, Dict, List, Optional, Tuple, Callable
from urllib.request import urlopen, Request

import streamlit as st
from PIL import Image, ImageOps

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card


# =============================================================================
# Session keys
# =============================================================================
SS_OBS = "tool6_obs_components"
SS_PHOTO_BYTES = "photo_bytes"
SS_PHOTO_THUMBS = "photo_thumbs"
SS_AUDIO_BYTES = "audio_bytes"
SS_LAST_ADDED_COMP = "tool6_last_added_component_idx"


# =============================================================================
# Google Sheet (Audio source)
# =============================================================================
AUDIO_SHEET_ID = "1XxWP-d3lIV4vSxjp-8fo-u9JW0QvsOBjbFkl2mQqApc"
AUDIO_SHEET_GID = 1945665091
AUDIO_TPM_COL_NAME = "TPM_ID"


# =============================================================================
# UI / Performance constants
# =============================================================================
THUMB_W = 360
THUMB_H = 240
THUMB_SIZE = (THUMB_W, THUMB_H)

# Picker (selection stage): keep it simple & mobile-safe
PICKER_COLS = 2
PICKER_PER_PAGE = 16

# Smart preload: fetch only a few thumbs from next page, time-budgeted
PRELOAD_NEXT_MAX_ITEMS = 6
PRELOAD_TIME_BUDGET_S = 0.25  # keep very small to avoid slowing UI


# =============================================================================
# Titles
# =============================================================================
DEFAULT_OBSERVATION_TITLES: List[str] = [
    "Construction of bore well and well protection structure:",
    "Supply and installation of the solar system:",
    "Construction of 60 m3 reservoir:",
    "Construction of 5 m3 reservoir for School:",
    "Construction of boundary wall:",
    "Construction of guard room and latrine:",
    "Construction of stand taps:",
]
DEFAULT_OBSERVATION_TITLES = list(dict.fromkeys(DEFAULT_OBSERVATION_TITLES))


# =============================================================================
# Helpers
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _k(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"t6.s3.{h}"


def _ensure_state() -> None:
    ss = st.session_state

    ss.setdefault(SS_OBS, [])
    if not isinstance(ss[SS_OBS], list):
        ss[SS_OBS] = []

    ss.setdefault(SS_PHOTO_BYTES, {})
    if not isinstance(ss[SS_PHOTO_BYTES], dict):
        ss[SS_PHOTO_BYTES] = {}

    ss.setdefault(SS_PHOTO_THUMBS, {})
    if not isinstance(ss[SS_PHOTO_THUMBS], dict):
        ss[SS_PHOTO_THUMBS] = {}

    ss.setdefault(SS_AUDIO_BYTES, {})
    if not isinstance(ss[SS_AUDIO_BYTES], dict):
        ss[SS_AUDIO_BYTES] = {}

    ss.setdefault(SS_LAST_ADDED_COMP, None)


def _ensure_component_schema(c: Dict[str, Any]) -> Dict[str, Any]:
    c.setdefault("comp_id", "")
    c.setdefault("title", "")
    c.setdefault("observations", [])
    c.setdefault("observations_valid", [])
    return c


def _ensure_obs_schema(it: Dict[str, Any]) -> Dict[str, Any]:
    it.setdefault("title_mode", "Select")
    it.setdefault("title_selected", "")
    it.setdefault("title_custom", "")
    it.setdefault("audio_url", "")
    it.setdefault("photos", [])  # [{"url":..., "text":...}]
    it.setdefault("photo_picker_locked", False)  # hide others only after Done selecting
    return it


def _obs_title_raw(it: Dict[str, Any]) -> str:
    it = _ensure_obs_schema(it)
    if it.get("title_mode") == "Custom":
        return _s(it.get("title_custom"))
    return _s(it.get("title_selected"))


def _numbered_title(section_no: str, global_idx_1based: int, raw_title: str) -> str:
    t = _s(raw_title)
    if not t:
        return ""
    return f"{section_no}.{global_idx_1based}. {t}"


def _normalize_photos(selected_urls: List[str], old_photos: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    old_map = {
        _s(p.get("url")): _s(p.get("text"))
        for p in (old_photos or [])
        if isinstance(p, dict) and _s(p.get("url"))
    }
    return [{"url": u, "text": old_map.get(u, "")} for u in selected_urls]


# =============================================================================
# Mutations
# =============================================================================
def _add_component() -> None:
    ss = st.session_state
    comps = ss.get(SS_OBS, [])
    if not isinstance(comps, list):
        comps = []

    comps.append(
        _ensure_component_schema(
            {
                "comp_id": "",
                "title": "",
                "observations": [_ensure_obs_schema({})],
                "observations_valid": [],
            }
        )
    )
    ss[SS_OBS] = comps
    ss[SS_LAST_ADDED_COMP] = len(comps) - 1


def _remove_component(idx: int) -> None:
    comps = st.session_state.get(SS_OBS, [])
    if isinstance(comps, list) and 0 <= idx < len(comps):
        comps.pop(idx)
        st.session_state[SS_OBS] = comps
        st.session_state[SS_LAST_ADDED_COMP] = min(idx, len(comps) - 1) if comps else None


def _add_observation(comp_idx: int) -> None:
    comps = st.session_state.get(SS_OBS, [])
    if not (isinstance(comps, list) and 0 <= comp_idx < len(comps)):
        return
    comp = _ensure_component_schema(comps[comp_idx])
    obs = comp.get("observations") or []
    obs.append(_ensure_obs_schema({}))
    comp["observations"] = obs
    comps[comp_idx] = comp
    st.session_state[SS_OBS] = comps
    st.session_state[SS_LAST_ADDED_COMP] = comp_idx


def _remove_observation(comp_idx: int, obs_idx: int) -> None:
    comps = st.session_state.get(SS_OBS, [])
    if not (isinstance(comps, list) and 0 <= comp_idx < len(comps)):
        return
    comp = _ensure_component_schema(comps[comp_idx])
    obs = comp.get("observations") or []
    if 0 <= obs_idx < len(obs):
        obs.pop(obs_idx)
    if not obs:
        obs = [_ensure_obs_schema({})]
    comp["observations"] = obs
    comps[comp_idx] = comp
    st.session_state[SS_OBS] = comps
    st.session_state[SS_LAST_ADDED_COMP] = comp_idx


# =============================================================================
# Photo-only URL filter
# =============================================================================
_IMG_EXT_RE = re.compile(r"\.(jpg|jpeg|png|webp|gif|bmp|tif|tiff)(\?|#|$)", re.IGNORECASE)
_AUD_EXT_RE = re.compile(r"\.(mp3|wav|m4a|aac|ogg|opus|flac)(\?|#|$)", re.IGNORECASE)
_NON_IMG_HINT_RE = re.compile(r"\.(pdf|doc|docx|xls|xlsx|csv|zip|rar)(\?|#|$)", re.IGNORECASE)


def _looks_like_image_url(url: str, label: str = "") -> bool:
    u = _s(url)
    if not u:
        return False
    low_u = u.lower()
    low_l = _s(label).lower()

    if _NON_IMG_HINT_RE.search(low_u):
        return False
    if _AUD_EXT_RE.search(low_u):
        return False

    if _IMG_EXT_RE.search(low_u):
        return True

    if "googleusercontent.com" in low_u or "lh3.googleusercontent.com" in low_u:
        return True
    if "photo" in low_l or "image" in low_l or "picture" in low_l:
        return True

    return False


def _filter_photo_urls(urls: List[str], labels: Dict[str, str]) -> List[str]:
    out: List[str] = []
    for u in (urls or []):
        if not _s(u):
            continue
        lab = _s(labels.get(u, ""))
        if _looks_like_image_url(u, lab):
            out.append(u)

    seen = set()
    res: List[str] = []
    for u in out:
        if u not in seen:
            seen.add(u)
            res.append(u)
    return res


# =============================================================================
# Audio detection + playback helpers
# =============================================================================
_AUD_URL_RE = re.compile(r"\.(mp3|wav|m4a|aac|ogg|opus|flac)(\?|#|$)", re.IGNORECASE)


def _looks_like_audio_url(url: str) -> bool:
    u = _s(url)
    if not u:
        return False
    low = u.lower()

    if _AUD_URL_RE.search(low):
        return True
    if "submission-attachment" in low and ("aac" in low or "m4a" in low or "mp3" in low or "wav" in low):
        return True
    if "audio" in low or "voice" in low or "record" in low:
        return True
    return False


def _guess_audio_mime(url: str, fallback: str = "audio/aac") -> str:
    low = _s(url).lower()
    if ".mp3" in low:
        return "audio/mpeg"
    if ".wav" in low:
        return "audio/wav"
    if ".m4a" in low:
        return "audio/mp4"
    if ".aac" in low:
        return "audio/aac"
    if ".ogg" in low:
        return "audio/ogg"
    if ".opus" in low:
        return "audio/opus"
    if ".flac" in low:
        return "audio/flac"
    return fallback


# =============================================================================
# Google Sheet audio lookup (API if available, else public CSV export)
# =============================================================================
def _get_google_sheets_service():
    """
    Optional. If googleapiclient is missing, we simply return None and use CSV export.
    """
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except Exception:
        return None

    sa = st.secrets.get("gcp_service_account")
    if not sa:
        return None

    creds = service_account.Credentials.from_service_account_info(
        sa,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


@st.cache_data(show_spinner=False, ttl=300)
def _sheet_title_by_gid_api(spreadsheet_id: str, gid: int) -> Optional[str]:
    svc = _get_google_sheets_service()
    if svc is None:
        return None
    try:
        meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sh in (meta.get("sheets") or []):
            props = (sh.get("properties") or {})
            if int(props.get("sheetId", -1)) == int(gid):
                return _s(props.get("title"))
        return None
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=120)
def _read_sheet_values_api(spreadsheet_id: str, sheet_title: str) -> List[List[str]]:
    svc = _get_google_sheets_service()
    if svc is None:
        return []
    rng = f"'{sheet_title}'!A1:ZZ5000"
    try:
        resp = svc.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=rng).execute()
        vals = resp.get("values") or []
        out: List[List[str]] = []
        for row in vals:
            out.append([_s(x) for x in (row or [])])
        return out
    except Exception:
        return []


@st.cache_data(show_spinner=False, ttl=120)
def _read_sheet_values_public_csv(spreadsheet_id: str, gid: int) -> List[List[str]]:
    """
    No extra packages. Works if sheet is readable via export endpoint.
    """
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={int(gid)}"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=12) as resp:
            txt = resp.read().decode("utf-8", errors="replace")
        reader = csv.reader(StringIO(txt))
        return [[_s(c) for c in row] for row in reader]
    except Exception:
        return []


def _discover_audio_from_google_sheet_by_tpm_id(tpm_id: str) -> Tuple[List[str], Dict[str, str], str]:
    tpm_id = _s(tpm_id)
    if not tpm_id:
        return [], {}, "No TPM_ID."

    # 1) API route if available
    svc = _get_google_sheets_service()
    if svc is not None:
        title = _sheet_title_by_gid_api(AUDIO_SHEET_ID, AUDIO_SHEET_GID)
        if title:
            values = _read_sheet_values_api(AUDIO_SHEET_ID, title)
            if values and len(values) >= 2:
                header = values[0]
                try:
                    tpm_col_idx = next(i for i, h in enumerate(header) if _s(h).upper() == AUDIO_TPM_COL_NAME.upper())
                except StopIteration:
                    return [], {}, "Audio sheet: TPM_ID column not found."

                for r in values[1:]:
                    if tpm_col_idx < len(r) and _s(r[tpm_col_idx]) == tpm_id:
                        urls: List[str] = []
                        label_by_url: Dict[str, str] = {}
                        for i, cell in enumerate(r):
                            u = _s(cell)
                            if u and _looks_like_audio_url(u):
                                col_name = _s(header[i]) if i < len(header) else "Audio"
                                if u not in label_by_url:
                                    urls.append(u)
                                    label_by_url[u] = col_name or "Audio"
                        return urls, label_by_url, "Audio loaded from Google Sheet (API)."

    # 2) CSV export route (no googleapiclient)
    values = _read_sheet_values_public_csv(AUDIO_SHEET_ID, AUDIO_SHEET_GID)
    if not values or len(values) < 2:
        return [], {}, "Audio not loaded: sheet export not accessible (check sharing)."

    header = values[0]
    try:
        tpm_col_idx = next(i for i, h in enumerate(header) if _s(h).upper() == AUDIO_TPM_COL_NAME.upper())
    except StopIteration:
        return [], {}, "Audio sheet: TPM_ID column not found."

    target: Optional[List[str]] = None
    for r in values[1:]:
        if tpm_col_idx < len(r) and _s(r[tpm_col_idx]) == tpm_id:
            target = r
            break
    if not target:
        return [], {}, "No audio links found for this TPM_ID row."

    urls: List[str] = []
    label_by_url: Dict[str, str] = {}
    for i, cell in enumerate(target):
        u = _s(cell)
        if u and _looks_like_audio_url(u):
            col_name = _s(header[i]) if i < len(header) else "Audio"
            if u not in label_by_url:
                urls.append(u)
                label_by_url[u] = col_name or "Audio"

    return urls, label_by_url, "Audio loaded from Google Sheet (CSV export)."


def _discover_audio(ctx: Tool6Context) -> Tuple[List[str], Dict[str, str], str]:
    tpm_id = _s(getattr(ctx, "tpm_id", ""))

    sheet_urls, sheet_labels, msg = _discover_audio_from_google_sheet_by_tpm_id(tpm_id)
    if sheet_urls:
        return sheet_urls, sheet_labels, msg

    # fallback (ctx.audios)
    audios = getattr(ctx, "audios", None)
    if isinstance(audios, list) and audios:
        urls: List[str] = []
        label_by_url: Dict[str, str] = {}
        for a in audios:
            if not isinstance(a, dict):
                continue
            u = _s(a.get("url"))
            field = _s(a.get("field"))
            if u and _looks_like_audio_url(u) and u not in label_by_url:
                urls.append(u)
                label_by_url[u] = field or "Audio"
        if urls:
            return urls, label_by_url, "Audio loaded from ctx.audios (fallback)."

    return [], {}, msg


# =============================================================================
# Thumbnails (fixed-size) + cache
# =============================================================================
def _make_thumbnail_fixed(img_bytes: bytes, *, size: Tuple[int, int] = THUMB_SIZE) -> Optional[bytes]:
    try:
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        thumb = ImageOps.fit(img, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        out = BytesIO()
        thumb.save(out, format="JPEG", quality=72, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _fetch_and_cache_image(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    url = _s(url)
    if not url:
        return

    ss = st.session_state
    photo_bytes: Dict[str, bytes] = ss.get(SS_PHOTO_BYTES, {}) or {}
    thumbs: Dict[str, bytes] = ss.get(SS_PHOTO_THUMBS, {}) or {}

    if url in photo_bytes and photo_bytes[url]:
        if url not in thumbs:
            th = _make_thumbnail_fixed(photo_bytes[url])
            if th:
                thumbs[url] = th
                ss[SS_PHOTO_THUMBS] = thumbs
        return

    ok, b, _msg = fetch_image(url)
    if ok and b:
        photo_bytes[url] = b
        ss[SS_PHOTO_BYTES] = photo_bytes

        th = _make_thumbnail_fixed(b)
        if th:
            thumbs[url] = th
            ss[SS_PHOTO_THUMBS] = thumbs


def _fetch_and_cache_audio(
    url: str,
    *,
    fetch_audio: Optional[Callable[[str], Tuple[bool, Optional[bytes], str, str]]],
) -> Tuple[Optional[bytes], str]:
    url = _s(url)
    if not url:
        return None, ""

    ss = st.session_state
    audio_bytes: Dict[str, bytes] = ss.get(SS_AUDIO_BYTES, {}) or {}

    if url in audio_bytes and audio_bytes[url]:
        return audio_bytes[url], _guess_audio_mime(url)

    if fetch_audio is None:
        return None, _guess_audio_mime(url)

    ok, b, _msg, mime = fetch_audio(url)
    if ok and b:
        audio_bytes[url] = b
        ss[SS_AUDIO_BYTES] = audio_bytes
        final_mime = (mime or _guess_audio_mime(url)).split(";")[0]
        return b, final_mime

    return None, _guess_audio_mime(url)


# =============================================================================
# Smart preload next page (time-budgeted)
# =============================================================================
def _preload_next_page_thumbs(
    *,
    filtered_urls: List[str],
    page_1based: int,
    per_page: int,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
    key_prefix: str,
) -> None:
    """
    ✅ Preloads a few thumbnails from the next page but stops quickly (time budget).
    Designed to NOT slow down UI.
    """
    if not filtered_urls:
        return

    start_next = int(page_1based) * int(per_page)
    if start_next >= len(filtered_urls):
        return

    ss = st.session_state
    thumbs: Dict[str, bytes] = ss.get(SS_PHOTO_THUMBS, {}) or {}

    next_urls = filtered_urls[start_next: start_next + PRELOAD_NEXT_MAX_ITEMS]
    t0 = time.perf_counter()

    for u in next_urls:
        if (time.perf_counter() - t0) > PRELOAD_TIME_BUDGET_S:
            break
        if u in thumbs:
            continue
        _fetch_and_cache_image(u, fetch_image=fetch_image)
        thumbs = ss.get(SS_PHOTO_THUMBS, {}) or {}


# =============================================================================
# Picker grid (fast) + responsive selected-only view
# =============================================================================
def _photo_picker_grid_fast(
    *,
    all_urls: List[str],
    labels: Dict[str, str],
    selected_urls: List[str],
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
    cols: int,
    per_page: int,
    key_prefix: str,
) -> List[str]:
    all_urls = [u for u in (all_urls or []) if _s(u)]
    selected = set([u for u in (selected_urls or []) if u in all_urls])

    def _label(u: str) -> str:
        return _s(labels.get(u) or u)

    q = st.text_input(
        "Search photos",
        value="",
        key=_k(key_prefix, "search"),
        placeholder="Search by name...",
        label_visibility="collapsed",
    ).strip().lower()

    filtered = [u for u in all_urls if (q in _label(u).lower())] if q else all_urls

    if not filtered:
        st.info("No photos match your search.")
        return [u for u in all_urls if u in selected]

    total = len(filtered)
    pages = max(1, (total + per_page - 1) // per_page)

    p1, p2, p3 = st.columns([0.34, 0.33, 0.33], gap="small")
    with p1:
        page = st.number_input(
            "Page",
            min_value=1,
            max_value=pages,
            value=1,
            step=1,
            key=_k(key_prefix, "page"),
            label_visibility="collapsed",
        )
    with p2:
        if st.button("Select page", use_container_width=True, key=_k(key_prefix, "sel_page")):
            start = (int(page) - 1) * per_page
            end = min(total, start + per_page)
            for u in filtered[start:end]:
                selected.add(u)
    with p3:
        st.caption(f"{len(selected)} selected")

    start = (int(page) - 1) * per_page
    end = min(total, start + per_page)
    chunk = filtered[start:end]

    thumbs: Dict[str, bytes] = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}

    rows = [chunk[i: i + cols] for i in range(0, len(chunk), cols)]
    for r in rows:
        grid = st.columns(cols, gap="small")
        for i, u in enumerate(r):
            with grid[i]:
                if u not in thumbs:
                    _fetch_and_cache_image(u, fetch_image=fetch_image)
                    thumbs = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}

                bts = thumbs.get(u)
                if bts:
                    st.image(bts, use_container_width=True)
                else:
                    st.caption("Preview not available")

                st.caption(_label(u))
                ck = st.checkbox("Select", value=(u in selected), key=_k(key_prefix, "ck", u))
                if ck:
                    selected.add(u)
                else:
                    selected.discard(u)

    # ✅ smart preload next page (budgeted)
    _preload_next_page_thumbs(
        filtered_urls=filtered,
        page_1based=int(page),
        per_page=per_page,
        fetch_image=fetch_image,
        key_prefix=key_prefix,
    )

    ordered = [u for u in all_urls if u in selected]
    return ordered


def _render_selected_only_grid_responsive(
    *,
    selected_urls: List[str],
    labels: Dict[str, str],
) -> None:
    """
    ✅ Responsive (no confusion):
      - Mobile: 2 columns
      - Laptop: 3 columns
      - Monitor: 4 columns
    Uses HTML/CSS grid to auto-adapt.
    """
    if not selected_urls:
        return

    thumbs: Dict[str, bytes] = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}

    # Ensure thumbs exist for selected only (fast)
    items_html: List[str] = []
    for u in selected_urls:
        tb = thumbs.get(u)
        if not tb:
            continue
        b64 = base64.b64encode(tb).decode("utf-8")
        cap = _s(labels.get(u, u))
        items_html.append(
            f"""
            <div class="t6card">
              <img src="data:image/jpeg;base64,{b64}" />
              <div class="t6cap">{cap}</div>
            </div>
            """
        )

    css = """
    <style>
      .t6grid{
        display:grid;
        grid-template-columns: repeat(2, minmax(0,1fr));
        gap: 10px;
        align-items:start;
      }
      @media (min-width: 900px){
        .t6grid{ grid-template-columns: repeat(3, minmax(0,1fr)); }
      }
      @media (min-width: 1200px){
        .t6grid{ grid-template-columns: repeat(4, minmax(0,1fr)); }
      }
      .t6card{
        border:1px solid rgba(255,255,255,0.08);
        border-radius:12px;
        overflow:hidden;
        background: rgba(255,255,255,0.02);
      }
      .t6card img{
        width:100%;
        height:auto;
        display:block;
      }
      .t6cap{
        padding:8px 10px;
        font-size:12px;
        opacity:0.85;
        line-height:1.2;
        word-break: break-word;
      }
    </style>
    """
    st.markdown("**Selected photos (only)**")
    st.markdown(css + f"<div class='t6grid'>{''.join(items_html)}</div>", unsafe_allow_html=True)


# =============================================================================
# Build valid observations global
# =============================================================================
def _build_valid_observations_global(
    section_no: str,
    observations: List[Dict[str, Any]],
    *,
    start_index_1based: int,
    photo_bytes_cache: Dict[str, bytes],
) -> Tuple[List[Dict[str, Any]], int]:
    valid: List[Dict[str, Any]] = []
    global_idx = int(start_index_1based)

    for it in (observations or []):
        if not isinstance(it, dict):
            continue
        it = _ensure_obs_schema(it)

        title_raw = _obs_title_raw(it)
        if not _s(title_raw):
            continue

        title_num = _numbered_title(section_no, global_idx, title_raw)
        if not title_num:
            continue

        photos_fixed: List[Dict[str, Any]] = []
        for p in (it.get("photos") or []):
            if isinstance(p, dict) and _s(p.get("url")):
                u = _s(p.get("url"))
                photos_fixed.append({"url": u, "text": _s(p.get("text")), "bytes": photo_bytes_cache.get(u)})

        valid.append(
            {
                "title": title_num,
                "text": "",
                "audio_url": _s(it.get("audio_url")),
                "photos": photos_fixed,
            }
        )
        global_idx += 1

    return valid, global_idx


# =============================================================================
# MAIN
# =============================================================================
def render_step(
    ctx: Tool6Context,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
    fetch_audio: Optional[Callable[[str], Tuple[bool, Optional[bytes], str, str]]] = None,
) -> bool:
    _ensure_state()

    st.subheader("Step 3 — Observations (Audio + Photos + Per-photo Observation)")

    raw_photo_urls = getattr(ctx, "all_photo_urls", []) or []
    photo_labels = getattr(ctx, "photo_label_by_url", {}) or {}
    photo_urls = _filter_photo_urls(raw_photo_urls, photo_labels)

    audio_url_list, audio_label_by_url, audio_source_msg = _discover_audio(ctx)

    with st.container(border=True):
        card_open(
            "Observations",
            subtitle="Pick title, play audio, select photos with preview, then write observation for each selected photo.",
            variant="lg-variant-green",
        )

        comps: List[Dict[str, Any]] = st.session_state[SS_OBS]

        show_photo_picker = st.toggle("Pick photos with preview", value=True, key=_k("show_picker"))

        if st.button("Clear all", use_container_width=True, key=_k("clear_all")):
            st.session_state[SS_OBS] = []
            st.session_state[SS_LAST_ADDED_COMP] = None
            comps = st.session_state[SS_OBS]

        if not comps:
            status_card("No components yet", "Use **Add component** (at the bottom) to start.", level="warning")

        st.divider()

        SECTION_NO = "5"
        global_obs_idx = 1
        last_added = st.session_state.get(SS_LAST_ADDED_COMP)

        for ci in range(len(comps)):
            comp = _ensure_component_schema(comps[ci])

            comp_title = _s(comp.get("title")) or f"Component {ci + 1}"
            comp_id = _s(comp.get("comp_id"))
            exp_title = f"{comp_id} — {comp_title}".strip(" —")

            expanded = (ci == last_added) if last_added is not None else (ci == 0)

            with st.expander(exp_title, expanded=expanded):
                top = st.columns([1, 1, 2], gap="small")
                with top[0]:
                    st.button("Remove component", use_container_width=True, key=_k("rm_comp", ci),
                              on_click=_remove_component, args=(ci,))
                with top[1]:
                    st.button("Add observation", use_container_width=True, key=_k("add_obs", ci),
                              on_click=_add_observation, args=(ci,))
                with top[2]:
                    st.caption("Write observation per photo. General observation is removed.")

                c1, c2 = st.columns([1, 1], gap="large")
                with c1:
                    comp["comp_id"] = st.text_input("Component ID (optional)", value=_s(comp.get("comp_id")), key=_k("comp_id", ci))
                with c2:
                    comp["title"] = st.text_input("Component title", value=_s(comp.get("title")), key=_k("comp_title", ci))

                st.divider()

                observations: List[Dict[str, Any]] = comp.get("observations") or []
                if not observations:
                    observations = [_ensure_obs_schema({})]

                for oi in range(len(observations)):
                    it = _ensure_obs_schema(observations[oi])

                    raw_title = _obs_title_raw(it)
                    numbered = _numbered_title(SECTION_NO, global_obs_idx, raw_title) if raw_title else ""
                    header_title = numbered if numbered else f"Observation {oi + 1}"

                    with st.container(border=True):
                        hdr = st.columns([3, 1], gap="small")
                        with hdr[0]:
                            st.markdown(f"**{header_title}**")
                        with hdr[1]:
                            st.button(
                                "Remove",
                                use_container_width=True,
                                key=_k("rm_obs", ci, oi),
                                on_click=_remove_observation,
                                args=(ci, oi),
                                disabled=(len(observations) <= 1),
                            )

                        # ✅ Audio (must play)
                        if audio_url_list:
                            st.caption(audio_source_msg)
                            a1, a2 = st.columns([2, 1], gap="small")
                            with a1:
                                cur_audio = _s(it.get("audio_url"))
                                opts = [""] + audio_url_list
                                idx = opts.index(cur_audio) if cur_audio in opts else 0
                                it["audio_url"] = st.selectbox(
                                    "Audio (optional)",
                                    options=opts,
                                    index=idx,
                                    format_func=lambda u: (audio_label_by_url.get(u, "Audio") if u else "None"),
                                    key=_k("audio_pick", ci, oi),
                                )
                            with a2:
                                st.caption("Play")
                                if it["audio_url"]:
                                    ab, mime = _fetch_and_cache_audio(it["audio_url"], fetch_audio=fetch_audio)
                                    # Prefer bytes playback (most reliable)
                                    if ab:
                                        st.audio(ab, format=mime or _guess_audio_mime(it["audio_url"]))
                                    else:
                                        # fallback to URL (may fail if needs auth)
                                        st.audio(it["audio_url"], format=_guess_audio_mime(it["audio_url"]))
                                else:
                                    st.caption("None")
                        else:
                            it["audio_url"] = ""
                            st.info(audio_source_msg or "No audio links found for this TPM_ID row.")

                        st.divider()

                        # Title
                        m1, m2 = st.columns([1, 2], gap="small")
                        with m1:
                            it["title_mode"] = st.radio(
                                "Title type",
                                options=["Select", "Custom"],
                                index=0 if it.get("title_mode") != "Custom" else 1,
                                key=_k("title_mode", ci, oi),
                                horizontal=True,
                            )
                        with m2:
                            if it["title_mode"] == "Select":
                                opts = [""] + DEFAULT_OBSERVATION_TITLES
                                cur = _s(it.get("title_selected"))
                                idx = opts.index(cur) if cur in opts else 0
                                it["title_selected"] = st.selectbox("Select title", options=opts, index=idx, key=_k("title_sel", ci, oi))
                                it["title_custom"] = ""
                            else:
                                it["title_custom"] = st.text_input("Custom title", value=_s(it.get("title_custom")), key=_k("title_custom", ci, oi))
                                it["title_selected"] = ""

                        title_final = _obs_title_raw(it)

                        # Photos + per-photo observation
                        if not photo_urls:
                            st.info("No image/photo URLs are available for this record.")
                            it["photos"] = []
                        else:
                            if not title_final:
                                st.warning("Select or enter a title to enable photo selection.")
                                selected_urls: List[str] = []
                            else:
                                prev_selected = [
                                    p.get("url") for p in (it.get("photos") or [])
                                    if isinstance(p, dict) and p.get("url") in photo_urls
                                ]

                                locked = bool(it.get("photo_picker_locked")) and bool(prev_selected)

                                # ✅ After Done selecting: show ONLY selected photos (responsive 2/3/4 cols)
                                if show_photo_picker and locked:
                                    for u in prev_selected:
                                        _fetch_and_cache_image(u, fetch_image=fetch_image)

                                    _render_selected_only_grid_responsive(
                                        selected_urls=prev_selected,
                                        labels=photo_labels,
                                    )

                                    cA, cB = st.columns([0.55, 0.45], gap="small")
                                    with cA:
                                        st.caption("Only selected photos are shown.")
                                    with cB:
                                        if st.button("Change selection", use_container_width=True, key=_k("chg_sel", ci, oi)):
                                            it["photo_picker_locked"] = False
                                            locked = False

                                    selected_urls = prev_selected

                                else:
                                    if show_photo_picker:
                                        st.markdown("**Pick photos (preview before selecting)**")
                                        selected_urls = _photo_picker_grid_fast(
                                            all_urls=photo_urls,
                                            labels=photo_labels,
                                            selected_urls=prev_selected,
                                            fetch_image=fetch_image,
                                            cols=PICKER_COLS,
                                            per_page=PICKER_PER_PAGE,
                                            key_prefix=_k("grid", ci, oi),
                                        )

                                        if selected_urls:
                                            if st.button("✅ Done selecting", use_container_width=True, key=_k("done_sel", ci, oi)):
                                                it["photo_picker_locked"] = True
                                                # Next rerun => grid hidden instantly
                                    else:
                                        selected_urls = st.multiselect(
                                            "Select photos for this observation",
                                            options=photo_urls,
                                            default=prev_selected,
                                            format_func=lambda u: photo_labels.get(u, u),
                                            key=_k("obs_photos", ci, oi),
                                        )
                                        if selected_urls:
                                            if st.button("✅ Done selecting", use_container_width=True, key=_k("done_sel_ms", ci, oi)):
                                                it["photo_picker_locked"] = True

                            for u in selected_urls:
                                _fetch_and_cache_image(u, fetch_image=fetch_image)

                            it["photos"] = _normalize_photos(selected_urls, it.get("photos") or [])

                            if it["photos"]:
                                st.markdown("**Observation for each selected photo**")
                                thumbs: Dict[str, bytes] = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}

                                for pj, ph in enumerate(it["photos"]):
                                    u = _s(ph.get("url"))
                                    lab = photo_labels.get(u, u)

                                    colA, colB = st.columns([1, 2], gap="small")
                                    with colA:
                                        st.caption(lab)
                                        tb = thumbs.get(u)
                                        if tb:
                                            st.image(tb, use_container_width=True)
                                        else:
                                            st.caption("Preview not available.")
                                    with colB:
                                        ph["text"] = st.text_area(
                                            "Observation",
                                            value=_s(ph.get("text")),
                                            height=90,
                                            key=_k("photo_obs", ci, oi, pj),
                                            placeholder="Write observation for this photo...",
                                        )

                        observations[oi] = it
                        if _s(title_final):
                            global_obs_idx += 1

                comp["observations"] = observations
                comps[ci] = comp

        # Build observations_valid
        photo_bytes_cache: Dict[str, bytes] = st.session_state.get(SS_PHOTO_BYTES, {}) or {}
        global_idx = 1
        for ci in range(len(comps)):
            comp = _ensure_component_schema(comps[ci])
            valid, global_idx = _build_valid_observations_global(
                "5",
                comp.get("observations") or [],
                start_index_1based=global_idx,
                photo_bytes_cache=photo_bytes_cache,
            )
            comp["observations_valid"] = valid
            comps[ci] = comp

        st.session_state[SS_OBS] = comps
        st.session_state["tool6_component_observations_final"] = comps

        total_valid = sum(len(c.get("observations_valid") or []) for c in comps if isinstance(c, dict))
        if total_valid > 0:
            status_card("Saved", f"{total_valid} observation(s) will be included in the report.", level="success")
        else:
            status_card("Saved", "No titled observations yet. Add/select a title to include items in the report.", level="warning")

        st.divider()

        # Add component at bottom (no scrolling up)
        b1, b2 = st.columns([0.70, 0.30], gap="small")
        with b1:
            st.caption("Add a new component here (no scrolling up).")
        with b2:
            st.button("➕ Add component", use_container_width=True, key=_k("add_comp_bottom"), on_click=_add_component)

        card_close()

    return total_valid > 0
