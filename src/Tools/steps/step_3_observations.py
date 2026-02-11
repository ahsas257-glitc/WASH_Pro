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
from PIL import Image, ImageEnhance, ImageOps

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card


# =============================================================================
# Session keys
# =============================================================================
SS_OBS = "tool6_obs_components"
SS_PHOTO_BYTES = "photo_bytes"        # FULL bytes only for selected
SS_PHOTO_THUMBS = "photo_thumbs"      # THUMB bytes for UI
SS_AUDIO_BYTES = "audio_bytes"
SS_LAST_ADDED_COMP = "tool6_last_added_component_idx"

# Image fetch cache (TTL)
SS_IMG_CACHE = "tool6_img_cache"      # {url: {"ts": float, "ok": bool, "bytes": b, "msg": str}}
SS_IMG_CACHE_CFG = "tool6_img_cache_cfg"

# UI state per observation (persistent selection + lock)
SS_PICK_SEL = "tool6_s3_sel"          # dict: {scope_key: [urls...]}
SS_PICK_LOCK = "tool6_s3_lock"        # dict: {scope_key: bool}
SS_PICK_FOCUS = "tool6_s3_focus"      # dict: {scope_key: bool}

# Audio playlist per observation
SS_AUDIO_PLAY = "tool6_s3_audio_play"  # dict: {scope_key: {"idx": int}}

# =============================================================================
# Google Sheet (Audio source)
# =============================================================================
AUDIO_SHEET_ID = "1XxxWP-d3lIV4vSxjp-8fo-u9JW0QvsOBjbFkl2mQqApc".replace("xxx", "WP")  # keep your id
AUDIO_SHEET_GID = 1945665091
AUDIO_TPM_COL_NAME = "TPM_ID"

# =============================================================================
# UI / Performance constants
# =============================================================================
GRID_COLS = 3
THUMB_BOX = 220
HOVER_HD_MAXPX = 1920
HOVER_HD_QUALITY = 88

IMG_TTL_OK = 20 * 60
IMG_TTL_FAIL = 90
IMG_CACHE_MAX_ITEMS = 600
IMG_MAX_MB = 25

# Adaptive HD:
HD_BUDGET_UNLOCKED = 60   # before Done: limit HD layers (fast)
HD_BUDGET_LOCKED = 120    # after Done: selected-only, safe to allow more

# =============================================================================
# Titles
# =============================================================================
DEFAULT_OBSERVATION_TITLES: List[str] = list(dict.fromkeys([
    "Construction of bore well and well protection structure:",
    "Supply and installation of the solar system:",
    "Construction of 60 m3 reservoir:",
    "Construction of 5 m3 reservoir for School:",
    "Construction of boundary wall:",
    "Construction of guard room and latrine:",
    "Construction of stand taps:",
]))


# =============================================================================
# Helpers
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _k(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    return "t6.s3." + hashlib.md5(raw.encode("utf-8")).hexdigest()


def _scope(ci: int, oi: int) -> str:
    return f"c{ci}.o{oi}"


def _inject_css() -> None:
    st.markdown(
        f"""
<style>
  [data-testid="stVerticalBlock"] {{ gap: 0.70rem; }}

  .t6-card {{
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 12px;
    overflow: hidden;
    background: rgba(255,255,255,0.02);
  }}

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
    display: block;
    transition: transform 160ms ease, opacity 120ms ease;
    transform: scale(1.0);
    opacity: 1;
  }}

  .t6-imgbox img.t6-hd {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
    opacity: 0;
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
    padding: 8px 10px 0 10px;
    font-size: 11px;
    opacity: .86;
    line-height: 1.2;
    text-align: right;
    min-height: 32px;
    word-break: break-word;
  }}

  .t6-actions {{
    padding: 10px 10px 12px 10px;
  }}

  .t6-obs-box {{
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px;
    padding: 14px 14px 10px 14px;
    background: rgba(255,255,255,0.02);
    margin-top: 10px;
    margin-bottom: 12px;
  }}

  .t6-bottombar {{
    position: sticky;
    bottom: 0;
    z-index: 50;
    padding: 10px 0 0 0;
    backdrop-filter: blur(8px);
  }}

  .t6-bottombar-inner {{
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(15,15,18,0.60);
    border-radius: 14px;
    padding: 10px;
  }}
</style>
""",
        unsafe_allow_html=True,
    )


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

    ss.setdefault(SS_IMG_CACHE, {})
    if not isinstance(ss[SS_IMG_CACHE], dict):
        ss[SS_IMG_CACHE] = {}

    ss.setdefault(SS_IMG_CACHE_CFG, {
        "ttl_ok": IMG_TTL_OK,
        "ttl_fail": IMG_TTL_FAIL,
        "max_items": IMG_CACHE_MAX_ITEMS,
        "max_mb": IMG_MAX_MB,
    })

    ss.setdefault(SS_PICK_SEL, {})
    if not isinstance(ss[SS_PICK_SEL], dict):
        ss[SS_PICK_SEL] = {}

    ss.setdefault(SS_PICK_LOCK, {})
    if not isinstance(ss[SS_PICK_LOCK], dict):
        ss[SS_PICK_LOCK] = {}

    ss.setdefault(SS_PICK_FOCUS, {})
    if not isinstance(ss[SS_PICK_FOCUS], dict):
        ss[SS_PICK_FOCUS] = {}

    ss.setdefault(SS_AUDIO_PLAY, {})
    if not isinstance(ss[SS_AUDIO_PLAY], dict):
        ss[SS_AUDIO_PLAY] = {}


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
    it.setdefault("photos", [])
    it.setdefault("photo_picker_locked", False)
    return it


def _obs_title_raw(it: Dict[str, Any]) -> str:
    it = _ensure_obs_schema(it)
    if it.get("title_mode") == "Custom":
        return _s(it.get("title_custom"))
    return _s(it.get("title_selected"))


def _numbered_title(section_no: str, global_idx_1based: int, raw_title: str) -> str:
    t = _s(raw_title)
    return f"{section_no}.{global_idx_1based}. {t}" if t else ""


def _normalize_photos(selected_urls: List[str], old_photos: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    old_map = {_s(p.get("url")): _s(p.get("text")) for p in (old_photos or []) if isinstance(p, dict) and _s(p.get("url"))}
    return [{"url": u, "text": old_map.get(u, "")} for u in (selected_urls or [])]


# =============================================================================
# Mutations
# =============================================================================
def _add_component() -> None:
    comps = st.session_state.get(SS_OBS, [])
    if not isinstance(comps, list):
        comps = []
    comps.append(_ensure_component_schema({
        "comp_id": "",
        "title": "",
        "observations": [_ensure_obs_schema({})],
        "observations_valid": [],
    }))
    st.session_state[SS_OBS] = comps
    st.session_state[SS_LAST_ADDED_COMP] = len(comps) - 1


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


def _clear_all() -> None:
    st.session_state[SS_OBS] = []
    st.session_state[SS_LAST_ADDED_COMP] = None
    st.session_state[SS_PICK_SEL] = {}
    st.session_state[SS_PICK_LOCK] = {}
    st.session_state[SS_PICK_FOCUS] = {}
    st.session_state[SS_AUDIO_PLAY] = {}


# =============================================================================
# Photo URLs filter
# =============================================================================
IMG_EXT = re.compile(r"\.(jpg|jpeg|png|webp|gif|bmp|tif|tiff)(\?|#|$)", re.I)


def _only_images(urls: List[str]) -> List[str]:
    out: List[str] = []
    for u in urls or []:
        u = _s(u)
        if not u:
            continue
        if IMG_EXT.search(u) or "googleusercontent.com" in u or "lh3.googleusercontent.com" in u:
            out.append(u)
    return list(dict.fromkeys(out))


# =============================================================================
# fetch_image TTL cache wrapper
# =============================================================================
def _fetch_image_cached(url: str, *, fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]]) -> Tuple[bool, Optional[bytes], str]:
    url = _s(url)
    if not url:
        return False, None, "Empty URL"

    ss = st.session_state
    cache: Dict[str, Dict[str, Any]] = ss.get(SS_IMG_CACHE, {}) or {}
    cfg = ss.get(SS_IMG_CACHE_CFG, {}) or {}

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


# =============================================================================
# Thumbs + Hover HD
# =============================================================================
def _make_thumb_contain(b: bytes, *, box: int = THUMB_BOX, quality: int = 82) -> Optional[bytes]:
    try:
        img = Image.open(BytesIO(b))
        img = ImageOps.exif_transpose(img).convert("RGB")
        img = ImageEnhance.Contrast(img).enhance(0.95)
        img = ImageEnhance.Brightness(img).enhance(0.97)
        img.thumbnail((box, box), Image.Resampling.LANCZOS)

        bg = Image.new("RGB", (box, box), (32, 32, 36))
        w, h = img.size
        bg.paste(img, ((box - w) // 2, (box - h) // 2))

        out = BytesIO()
        bg.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _make_hover_hd(b: bytes, *, max_px: int = HOVER_HD_MAXPX, quality: int = HOVER_HD_QUALITY) -> Optional[bytes]:
    try:
        img = Image.open(BytesIO(b))
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
        return (
            f"<div class='t6-card'>"
            f"  <div class='t6-imgbox'></div>"
            f"  <div class='t6-cap'>{cap}</div>"
            f"</div>"
        )

    b64t = _b64_bytes(thumb_bytes)
    thumb_tag = f"<img class='t6-thumb' loading='lazy' src='data:image/jpeg;base64,{b64t}'/>"

    hd_tag = ""
    if hd_bytes:
        b64h = _b64_bytes(hd_bytes)
        hd_tag = f"<img class='t6-hd' loading='lazy' src='data:image/jpeg;base64,{b64h}'/>"

    return (
        f"<div class='t6-card'>"
        f"  <div class='t6-imgbox'>"
        f"    {thumb_tag}"
        f"    {hd_tag}"
        f"  </div>"
        f"  <div class='t6-cap'>{cap}</div>"
        f"</div>"
    )


def _fetch_thumb_and_optional_hd(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
    want_hd: bool,
) -> Tuple[Optional[bytes], Optional[bytes]]:
    url = _s(url)
    if not url:
        return None, None

    ss = st.session_state
    thumbs: Dict[str, bytes] = ss.get(SS_PHOTO_THUMBS, {}) or {}

    th = thumbs.get(url)
    hd: Optional[bytes] = None

    # thumb missing => download once (cached), create thumb (and maybe hd)
    if not th:
        ok, b, _ = _fetch_image_cached(url, fetch_image=fetch_image)
        if ok and b:
            th = _make_thumb_contain(b)
            if th:
                thumbs[url] = th
                ss[SS_PHOTO_THUMBS] = thumbs
            if want_hd:
                hd = _make_hover_hd(b)
        return th, hd

    # thumb exists, need hd => download (cached) then hd
    if want_hd:
        ok, b, _ = _fetch_image_cached(url, fetch_image=fetch_image)
        if ok and b:
            hd = _make_hover_hd(b)

    return th, hd


def _ensure_full_bytes_selected(url: str, *, fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]]) -> None:
    url = _s(url)
    if not url:
        return
    ss = st.session_state
    pb: Dict[str, bytes] = ss.get(SS_PHOTO_BYTES, {}) or {}
    if url in pb and pb[url]:
        return
    ok, b, _ = _fetch_image_cached(url, fetch_image=fetch_image)
    if ok and b:
        pb[url] = b
        ss[SS_PHOTO_BYTES] = pb


# =============================================================================
# Audio helpers (playlist in-app)
# =============================================================================
_AUD_URL_RE = re.compile(r"\.(mp3|wav|m4a|aac|ogg|opus|flac)(\?|#|$)", re.IGNORECASE)


def _looks_like_audio_url(url: str) -> bool:
    low = _s(url).lower()
    if not low:
        return False
    if _AUD_URL_RE.search(low):
        return True
    if "submission-attachment" in low and any(x in low for x in ("aac", "m4a", "mp3", "wav", "ogg", "opus", "flac")):
        return True
    if any(x in low for x in ("audio", "voice", "record")):
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


def _get_google_sheets_service():
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
        return [[_s(x) for x in (row or [])] for row in vals]
    except Exception:
        return []


@st.cache_data(show_spinner=False, ttl=120)
def _read_sheet_values_public_csv(spreadsheet_id: str, gid: int) -> List[List[str]]:
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
                        return urls, label_by_url, "Audio loaded from Google Sheet."

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

    return urls, label_by_url, ""


def _discover_audio(ctx: Tool6Context) -> Tuple[List[str], Dict[str, str], str]:
    tpm_id = _s(getattr(ctx, "tpm_id", ""))
    sheet_urls, sheet_labels, msg = _discover_audio_from_google_sheet_by_tpm_id(tpm_id)
    if sheet_urls:
        return sheet_urls, sheet_labels, msg

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
            return urls, label_by_url, "Audio loaded from ctx.audios."

    return [], {}, msg


@st.fragment
def _audio_playlist_block(
    *,
    audio_urls: List[str],
    audio_label_by_url: Dict[str, str],
    source_msg: str,
    it: Dict[str, Any],
    scope_key: str,
) -> None:
    if not audio_urls:
        it["audio_url"] = ""
        st.info(source_msg or "No audio links found.")
        return

    st.caption(source_msg)

    ss = st.session_state
    play = (ss.get(SS_AUDIO_PLAY) or {})
    if scope_key not in play or not isinstance(play.get(scope_key), dict):
        play[scope_key] = {"idx": 0}
        ss[SS_AUDIO_PLAY] = play

    idx = int(play[scope_key].get("idx") or 0)
    idx = max(0, min(idx, len(audio_urls) - 1))

    # If it has a selected url, sync index
    cur_audio = _s(it.get("audio_url"))
    if cur_audio in audio_urls:
        idx = audio_urls.index(cur_audio)

    c1, c2, c3 = st.columns([1, 2, 1], gap="small")
    with c1:
        if st.button("⏮ Prev", use_container_width=True, key=_k("aud_prev", scope_key)):
            idx = (idx - 1) % len(audio_urls)
    with c3:
        if st.button("Next ⏭", use_container_width=True, key=_k("aud_next", scope_key)):
            idx = (idx + 1) % len(audio_urls)

    with c2:
        pick = st.selectbox(
            "Audio playlist",
            options=list(range(len(audio_urls))),
            index=idx,
            format_func=lambda i: _s(audio_label_by_url.get(audio_urls[i], f"Track {i+1}")),
            key=_k("aud_pick", scope_key),
        )
        idx = int(pick)

    play[scope_key]["idx"] = idx
    ss[SS_AUDIO_PLAY] = play

    it["audio_url"] = audio_urls[idx]
    st.audio(it["audio_url"], format=_guess_audio_mime(it["audio_url"]))


# =============================================================================
# Picker: persistent Select/Remove + Done hides others
# =============================================================================
def _sel_get(scope_key: str) -> List[str]:
    ss = st.session_state
    d = ss.get(SS_PICK_SEL, {}) or {}
    v = d.get(scope_key, [])
    if isinstance(v, list):
        return [_s(x) for x in v if _s(x)]
    return []


def _sel_set(scope_key: str, urls: List[str]) -> None:
    ss = st.session_state
    d = ss.get(SS_PICK_SEL, {}) or {}
    d[scope_key] = list(dict.fromkeys([_s(x) for x in (urls or []) if _s(x)]))
    ss[SS_PICK_SEL] = d


def _lock_get(scope_key: str) -> bool:
    ss = st.session_state
    d = ss.get(SS_PICK_LOCK, {}) or {}
    return bool(d.get(scope_key, False))


def _lock_set(scope_key: str, v: bool) -> None:
    ss = st.session_state
    d = ss.get(SS_PICK_LOCK, {}) or {}
    d[scope_key] = bool(v)
    ss[SS_PICK_LOCK] = d


def _focus_get(scope_key: str) -> bool:
    ss = st.session_state
    d = ss.get(SS_PICK_FOCUS, {}) or {}
    return bool(d.get(scope_key, True))


def _focus_set(scope_key: str, v: bool) -> None:
    ss = st.session_state
    d = ss.get(SS_PICK_FOCUS, {}) or {}
    d[scope_key] = bool(v)
    ss[SS_PICK_FOCUS] = d


def _render_photo_picker(
    *,
    urls: List[str],
    labels: Dict[str, str],
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
    scope_key: str,
) -> Tuple[List[str], bool]:
    urls = [u for u in (urls or []) if _s(u)]

    def lab(u: str) -> str:
        return _s(labels.get(u, u))

    selected = [u for u in _sel_get(scope_key) if u in urls]
    selected_set = set(selected)

    locked = _lock_get(scope_key)
    focus_selected = _focus_get(scope_key)

    # If locked -> show only selected
    show_urls = selected if locked else (selected if (selected and focus_selected) else urls)

    # Adaptive HD budget (fast)
    hd_budget = (HD_BUDGET_LOCKED if locked else HD_BUDGET_UNLOCKED)
    hd_budget = min(hd_budget, len(show_urls))
    hd_set = set(show_urls[:hd_budget])

    # Header row
    h1, h2, h3 = st.columns([1.0, 1.2, 1.0], gap="small")
    with h1:
        st.caption(f"Selected: {len(selected)}")
    with h2:
        if (not locked) and selected:
            _focus_set(scope_key, st.toggle("Focus selected", value=focus_selected, key=_k("focus", scope_key)))
    with h3:
        if locked and selected:
            if st.button("Edit", use_container_width=True, key=_k("unlock", scope_key)):
                _lock_set(scope_key, False)
                _focus_set(scope_key, False)
                st.rerun()

    cols = GRID_COLS
    for i in range(0, len(show_urls), cols):
        row = show_urls[i:i + cols]
        columns = st.columns(cols, gap="small")

        for col, url in zip(columns, row):
            with col:
                want_hd = url in hd_set
                th, hd = _fetch_thumb_and_optional_hd(url, fetch_image=fetch_image, want_hd=want_hd)
                st.markdown(_card_html_with_hover(th, hd, lab(url)), unsafe_allow_html=True)

                if locked:
                    continue

                st.markdown("<div class='t6-actions'>", unsafe_allow_html=True)

                is_sel = (url in selected_set)
                btn_label = "Remove" if is_sel else "Select"
                url_index = urls.index(url)  # stable index inside urls list
                if st.button(btn_label, use_container_width=True, key=_k("selbtn", scope_key, url_index)):

                    if is_sel:
                        selected_set.discard(url)
                    else:
                        selected_set.add(url)

                    # keep original order of urls
                    new_sel = [u for u in urls if u in selected_set]
                    _sel_set(scope_key, new_sel)
                    st.rerun()

                st.markdown("</div>", unsafe_allow_html=True)

    selected = [u for u in urls if u in set(_sel_get(scope_key))]

    if not locked:
        c1, c2 = st.columns([1, 1], gap="small")
        with c1:
            if st.button("Done", use_container_width=True, disabled=(len(selected) == 0), key=_k("done", scope_key)):
                for u in selected:
                    _ensure_full_bytes_selected(u, fetch_image=fetch_image)
                _lock_set(scope_key, True)
                st.rerun()
        with c2:
            if selected and st.button("Show all", use_container_width=True, key=_k("showall", scope_key)):
                _focus_set(scope_key, False)
                st.rerun()

    return selected, locked


# =============================================================================
# Notes: right image, left text (fast + full quality)
# =============================================================================
def _sync_photo_text(ci: int, oi: int, pj: int, widget_key: str) -> None:
    ss = st.session_state
    comps = ss.get(SS_OBS, [])
    if not (isinstance(comps, list) and 0 <= ci < len(comps)):
        return

    comp = _ensure_component_schema(comps[ci])
    obs = comp.get("observations") or []
    if not (0 <= oi < len(obs)):
        return

    it = _ensure_obs_schema(obs[oi])
    photos = it.get("photos") or []
    if not (0 <= pj < len(photos)):
        return

    if isinstance(photos[pj], dict):
        photos[pj]["text"] = _s(ss.get(widget_key))
        it["photos"] = photos
        obs[oi] = it
        comp["observations"] = obs
        comps[ci] = comp
        ss[SS_OBS] = comps


@st.fragment
def _photo_notes_block(
    *,
    it: Dict[str, Any],
    photo_labels: Dict[str, str],
    ci: int,
    oi: int,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    if not it.get("photos"):
        return

    ss = st.session_state
    pb: Dict[str, bytes] = ss.get(SS_PHOTO_BYTES, {}) or {}

    for pj, ph in enumerate(it["photos"]):
        u = _s(ph.get("url"))
        lab = _s(photo_labels.get(u, u))

        if u:
            _ensure_full_bytes_selected(u, fetch_image=fetch_image)
            pb = ss.get(SS_PHOTO_BYTES, {}) or {}

        # Left = text, Right = image
        col_text, col_img = st.columns([2, 1], gap="small")
        with col_img:
            b = pb.get(u)
            if b:
                st.image(b, caption=lab, use_container_width=True)
            else:
                st.caption(lab)
                st.caption("Image unavailable.")

        with col_text:
            key_txt = _k("photo_obs", ci, oi, pj)
            if key_txt not in ss:
                ss[key_txt] = _s(ph.get("text"))

            st.text_area(
                "Observation",
                key=key_txt,
                height=110,
                placeholder="Write observation for this photo...",
                on_change=lambda ci=ci, oi=oi, pj=pj, key_txt=key_txt: _sync_photo_text(ci, oi, pj, key_txt),
            )


# =============================================================================
# Build final valid observations
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

        valid.append({"title": title_num, "text": "", "audio_url": _s(it.get("audio_url")), "photos": photos_fixed})
        global_idx += 1

    return valid, global_idx


# =============================================================================
# MAIN
# =============================================================================
def render_step(
    ctx: Tool6Context,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> bool:
    _ensure_state()
    _inject_css()

    raw_photo_urls = getattr(ctx, "all_photo_urls", []) or []
    photo_labels = getattr(ctx, "photo_label_by_url", {}) or {}
    photo_urls = _only_images(raw_photo_urls)

    audio_urls, audio_label_by_url, audio_source_msg = _discover_audio(ctx)

    card_open("Observations", variant="lg-variant-green")

    comps: List[Dict[str, Any]] = st.session_state[SS_OBS]
    if not comps:
        status_card("No components yet", "Use **Add component** below to start.", level="warning")

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
            top = st.columns([1.1, 1.1, 1.8], gap="small")
            with top[0]:
                st.button("Remove component", use_container_width=True, key=_k("rm_comp", ci), on_click=_remove_component, args=(ci,))
            with top[1]:
                st.button("Add observation", use_container_width=True, key=_k("add_obs", ci), on_click=_add_observation, args=(ci,))

            st.divider()

            observations: List[Dict[str, Any]] = comp.get("observations") or []
            if not observations:
                observations = [_ensure_obs_schema({})]

            for oi in range(len(observations)):
                it = _ensure_obs_schema(observations[oi])

                raw_title = _obs_title_raw(it)
                numbered = _numbered_title(SECTION_NO, global_obs_idx, raw_title) if raw_title else ""
                header_title = numbered if numbered else f"Observation {oi + 1}"
                scope_key = _scope(ci, oi)

                st.markdown("<div class='t6-obs-box'>", unsafe_allow_html=True)

                hdr = st.columns([3, 1], gap="small")
                with hdr[0]:
                    st.markdown(f"**{header_title}**")
                with hdr[1]:
                    st.button("Remove", use_container_width=True, key=_k("rm_obs", ci, oi), on_click=_remove_observation, args=(ci, oi))

                _audio_playlist_block(
                    audio_urls=audio_urls,
                    audio_label_by_url=audio_label_by_url,
                    source_msg=audio_source_msg,
                    it=it,
                    scope_key=scope_key,
                )

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
                st.divider()

                # Photos
                if not photo_urls:
                    st.info("No image/photo URLs are available for this record.")
                    it["photos"] = []
                    it["photo_picker_locked"] = False
                else:
                    if not title_final:
                        st.warning("Select or enter a title to enable photo selection.")
                        it["photos"] = []
                        it["photo_picker_locked"] = False
                    else:
                        # render picker with persistent selection state
                        st.markdown("**Photos**")

                        selected_urls, locked = _render_photo_picker(
                            urls=photo_urls,
                            labels=photo_labels,
                            fetch_image=fetch_image,
                            scope_key=scope_key,
                        )

                        it["photo_picker_locked"] = bool(locked)
                        it["photos"] = _normalize_photos(selected_urls, it.get("photos") or [])

                        # show notes only when locked OR when there are selected urls
                        if selected_urls:
                            _photo_notes_block(
                                it=it,
                                photo_labels=photo_labels,
                                ci=ci,
                                oi=oi,
                                fetch_image=fetch_image,
                            )

                st.markdown("</div>", unsafe_allow_html=True)

                observations[oi] = it
                if _s(title_final):
                    global_obs_idx += 1

            comp["observations"] = observations
            comps[ci] = comp

    # Build valid observations
    photo_bytes_cache: Dict[str, bytes] = st.session_state.get(SS_PHOTO_BYTES, {}) or {}
    global_idx = 1
    for ci in range(len(comps)):
        comp = _ensure_component_schema(comps[ci])
        valid, global_idx = _build_valid_observations_global(
            SECTION_NO,
            comp.get("observations") or [],
            start_index_1based=global_idx,
            photo_bytes_cache=photo_bytes_cache,
        )
        comp["observations_valid"] = valid
        comps[ci] = comp

    st.session_state[SS_OBS] = comps
    st.session_state["tool6_component_observations_final"] = comps

    total_valid = sum(len(c.get("observations_valid") or []) for c in comps if isinstance(c, dict))

    # Bottom sticky actions
    st.markdown("<div class='t6-bottombar'><div class='t6-bottombar-inner'>", unsafe_allow_html=True)
    b1, b2, b3 = st.columns([1, 1, 2], gap="small")
    with b1:
        st.button("Clear all", use_container_width=True, key=_k("clear_all_bottom"), on_click=_clear_all)
    with b2:
        st.button("➕ Add component", use_container_width=True, key=_k("add_comp_bottom"), on_click=_add_component)

    st.divider()
    card_close()
    return total_valid > 0
