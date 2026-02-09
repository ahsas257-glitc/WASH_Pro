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
from PIL import Image, ImageEnhance

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card

SS_AUDIO_THUMBS = "audio_thumbs"      # small bytes (optional)
SS_AUDIO_LOCKS = "audio_picker_locked"  # per observation lock state (optional global)

# =============================================================================
# Session keys
# =============================================================================
SS_OBS = "tool6_obs_components"
SS_PHOTO_BYTES = "photo_bytes"        # FULL bytes only for selected (report)
SS_PHOTO_THUMBS = "photo_thumbs"      # THUMB bytes for UI
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
TILE = 120               # like Step4 small square feel
GRID_COLS = 3            # like Step4
THUMB_BOX = 220          # better contain canvas like Step4
PREFETCH_LIMIT = 36      # Step4 prefetch visible set


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
def _audio_card_html(label: str) -> str:
    # فقط یک placeholder داخل کارت، پلیر را خود streamlit داخل col می‌گذاریم
    cap = _s(label)
    return (
        f"<div class='t6-card'>"
        f"  <div class='t6-audio-box'>"
        f"    <div class='t6-audio-icon'>🔊</div>"
        f"  </div>"
        f"  <div class='t6-cap'>{cap}</div>"
        f"</div>"
    )

def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _k(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"t6.s3.{h}"


def _download_bytes_urlopen(url: str, timeout: int = 25, max_mb: int = 40) -> Tuple[bool, Optional[bytes], str, str]:
    """
    Robust downloader for public/accessible URLs (handles redirects).
    Returns: (ok, bytes, mime, message)

    Notes:
    - Uses stronger headers for services like SurveyCTO.
    - Enforces a max download size to avoid huge downloads.
    """
    url = _s(url)
    if not url:
        return False, None, "", "Empty URL"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        # Some hosts behave better with a referer:
        "Referer": "https://act4performance.surveycto.com/",
    }

    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as resp:
            mime = _s(resp.headers.get("Content-Type")).split(";")[0].strip()
            clen = resp.headers.get("Content-Length")
            if clen:
                try:
                    size = int(clen)
                    if size > max_mb * 1024 * 1024:
                        return False, None, mime, f"Audio too large ({size/1024/1024:.1f} MB)"
                except Exception:
                    pass

            data = resp.read()
            if data and len(data) > max_mb * 1024 * 1024:
                return False, None, mime, f"Audio too large ({len(data)/1024/1024:.1f} MB)"

            if not data:
                return False, None, mime, "Downloaded 0 bytes"
            return True, data, mime, "OK"

    except Exception as e:
        return False, None, "", f"Download failed: {e}"


# =============================================================================
# CSS (MATCH Step4 look/behavior)
# =============================================================================
def _inject_css() -> None:
    st.markdown(
        f"""
        <style>
          [data-testid="stVerticalBlock"] {{ gap: 0.70rem; }}

          /* RTL grid like Step4 cover */
          .t6-grid {{
            direction: rtl;
            display:grid;
            grid-template-columns: repeat({GRID_COLS}, minmax(0, 1fr));
            gap: 12px;
            align-items: start;
          }}

          .t6-card {{
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 12px;
            overflow: hidden;
            background: rgba(255,255,255,0.02);
          }}

          /* ✅ SQUARE thumbnail area */
          .t6-imgbox {{
            width: 100%;
            aspect-ratio: 1 / 1;               /* ✅ always square */
            background: rgba(0,0,0,0.08);
            display: grid;
            place-items: center;
          }}

          /* ✅ image fits fully inside the square */
          .t6-imgbox img {{
            width: 100%;
            height: 100%;
            object-fit: contain;               /* ✅ no crop */
            display: block;
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

          /* ✅ spacing for buttons area under each card */
          .t6-actions {{
            padding: 10px 10px 12px 10px;
          }}

          .t6-box {{
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 14px;
            padding: 14px;
            background: rgba(255,255,255,0.02);
            margin-top: 10px;
            margin-bottom: 12px;
          }}

          .t6-obs-box {{
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 14px;
            padding: 14px 14px 10px 14px;
            background: rgba(255,255,255,0.02);
            margin-top: 10px;
            margin-bottom: 12px;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )



# =============================================================================
# State
# =============================================================================
def _ensure_state() -> None:
    ss = st.session_state
    ss.setdefault(SS_AUDIO_THUMBS, {})
    if not isinstance(ss[SS_AUDIO_THUMBS], dict):
        ss[SS_AUDIO_THUMBS] = {}

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
    it.setdefault("photo_picker_locked", False)  # ✅ Step4-like lock
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
# Photo-only URL filter (ONLY IMAGES)
# =============================================================================
IMG_EXT = re.compile(r"\.(jpg|jpeg|png|webp|gif|bmp|tif|tiff)(\?|#|$)", re.I)


def _only_images(urls: List[str]) -> List[str]:
    out: List[str] = []
    for u in urls or []:
        u = _s(u)
        if not u:
            continue
        if IMG_EXT.search(u):
            out.append(u)
            continue
        if "googleusercontent.com" in u or "lh3.googleusercontent.com" in u:
            out.append(u)
            continue
    return list(dict.fromkeys(out))


# =============================================================================
# Audio helpers (unchanged)
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


def _fetch_and_cache_audio(
    url: str,
    *,
    fetch_audio: Optional[Callable[[str], Tuple[bool, Optional[bytes], str, str]]],
) -> Tuple[Optional[bytes], str]:
    """
    Always attempts to download and cache audio bytes, then play from bytes.
    Returns (bytes, mime). If bytes is None, caller should show an error (NOT play from URL).
    """
    url = _s(url)
    if not url:
        return None, ""

    ss = st.session_state
    audio_cache: Dict[str, Dict[str, Any]] = ss.get(SS_AUDIO_BYTES, {}) or {}

    # cache schema: { url: {"bytes": b"...", "mime": "audio/mp4"} }
    cached = audio_cache.get(url) or {}
    if isinstance(cached, dict) and cached.get("bytes"):
        return cached["bytes"], _s(cached.get("mime")) or _guess_audio_mime(url)

    # 1) Try provided fetch_audio (if exists)
    if fetch_audio is not None:
        try:
            ok, b, _msg, mime = fetch_audio(url)
            if ok and b:
                mime_clean = (_s(mime).split(";")[0].strip() or _guess_audio_mime(url))
                audio_cache[url] = {"bytes": b, "mime": mime_clean}
                ss[SS_AUDIO_BYTES] = audio_cache
                return b, mime_clean
        except Exception:
            pass

    # 2) Fallback: robust urlopen downloader
    ok2, b2, mime2, msg2 = _download_bytes_urlopen(url, timeout=25, max_mb=40)
    if ok2 and b2:
        mime_clean = (_s(mime2).split(";")[0].strip() or _guess_audio_mime(url))
        audio_cache[url] = {"bytes": b2, "mime": mime_clean}
        ss[SS_AUDIO_BYTES] = audio_cache
        return b2, mime_clean

    # If download failed, we return None to avoid playing by URL (private links often fail)
    return None, _guess_audio_mime(url)



# =============================================================================
# Google Sheet audio lookup (unchanged)
# =============================================================================
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
        out: List[List[str]] = []
        for row in vals:
            out.append([_s(x) for x in (row or [])])
        return out
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
                        return urls, label_by_url, "Audio loaded from Google Sheet (API)."

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
            return urls, label_by_url, "Audio loaded from ctx.audios (fallback)."

    return [], {}, msg


# =============================================================================
# Thumbs (MATCH Step4: contain + anti-glare + dark bg)
# =============================================================================
def _make_thumb_contain(b: bytes, *, box: int = THUMB_BOX, quality: int = 82) -> Optional[bytes]:
    try:
        img = Image.open(BytesIO(b)).convert("RGB")

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


def _thumb_html(thumb_bytes: bytes, caption: str) -> str:
    b64 = base64.b64encode(thumb_bytes).decode("utf-8")
    cap = _s(caption)
    return (
        f"<div class='t6-card'>"
        f"  <div class='t6-imgbox'>"
        f"    <img src='data:image/jpeg;base64,{b64}'/>"
        f"  </div>"
        f"  <div class='t6-cap'>{cap}</div>"
        f"</div>"
    )



def _fetch_thumb_only(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    url = _s(url)
    if not url:
        return

    ss = st.session_state
    thumbs: Dict[str, bytes] = ss.get(SS_PHOTO_THUMBS, {}) or {}
    if url in thumbs and thumbs[url]:
        return

    ok, b, _msg = fetch_image(url)
    if ok and b:
        th = _make_thumb_contain(b)
        if th:
            thumbs[url] = th
            ss[SS_PHOTO_THUMBS] = thumbs


def _ensure_full_bytes_selected(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    """
    ✅ Full bytes فقط برای عکس‌های انتخاب‌شده (برای گزارش).
    """
    url = _s(url)
    if not url:
        return
    ss = st.session_state
    photo_bytes: Dict[str, bytes] = ss.get(SS_PHOTO_BYTES, {}) or {}
    if url in photo_bytes and photo_bytes[url]:
        return

    ok, b, _msg = fetch_image(url)
    if ok and b:
        photo_bytes[url] = b
        ss[SS_PHOTO_BYTES] = photo_bytes


# =============================================================================
# Step4-like Picker (Select/Remove + Done/Change + show selected only)
# =============================================================================
def _render_photo_picker_step4_style(
    *,
    urls: List[str],
    labels: Dict[str, str],
    selected_urls: List[str],
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
    locked_flag: bool,
    scope_key: str,
) -> Tuple[List[str], bool]:
    urls = [u for u in (urls or []) if _s(u)]
    thumbs: Dict[str, bytes] = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}

    def get_label(u: str) -> str:
        return _s(labels.get(u, u))

    # ✅ multi-select state (preserve original order)
    selected_set = set([u for u in (selected_urls or []) if u in urls])
    selected = [u for u in urls if u in selected_set]

    is_locked_row = bool(locked_flag and selected)

    # Header
    h1, h2, h3 = st.columns([1, 1, 1])
    with h1:
        st.caption(f"Total: {len(urls)}")
    with h2:
        st.caption(f"Selected: {len(selected)}")
    with h3:
        if is_locked_row and selected:
            if st.button("Change selection", key=_k("chg", scope_key), use_container_width=True):
                is_locked_row = False
                st.rerun()

    # show all when unlocked, only selected when locked
    show_urls = selected if (is_locked_row and selected) else urls

    # prefetch thumbs
    for u in show_urls[:PREFETCH_LIMIT]:
        if u not in thumbs:
            _fetch_thumb_only(u, fetch_image=fetch_image)
            thumbs = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}

    # Grid
    cols = GRID_COLS
    for i in range(0, len(show_urls), cols):
        row = show_urls[i:i + cols]
        columns = st.columns(cols)
        for col, url in zip(columns, row + [None] * (cols - len(row))):
            with col:
                if not url:
                    continue

                tb = thumbs.get(url)
                if tb:
                    st.markdown(_thumb_html(tb, get_label(url)), unsafe_allow_html=True)
                else:
                    st.caption("Preview unavailable")
                    st.caption(get_label(url))

                is_selected = url in selected_set

                # ✅ can Select many, and Remove any time (until locked)
                if not is_locked_row:
                    st.markdown("<div class='t6-actions'>", unsafe_allow_html=True)

                    if not is_selected:
                        if st.button("Select", key=_k("sel", scope_key, url), use_container_width=True):
                            selected_set.add(url)
                            selected = [u for u in urls if u in selected_set]  # keep original order
                            st.rerun()
                    else:
                        if st.button("Remove", key=_k("rm", scope_key, url), use_container_width=True):
                            selected_set.discard(url)
                            selected = [u for u in urls if u in selected_set]
                            st.rerun()

                    st.markdown("</div>", unsafe_allow_html=True)

    # Done selecting
    if not is_locked_row:
        if st.button(
            "✅ Done selecting",
            use_container_width=True,
            disabled=(len(selected) == 0),
            key=_k("done", scope_key),
        ):
            # ✅ cache full bytes only for selected
            for u in selected:
                _ensure_full_bytes_selected(u, fetch_image=fetch_image)

            is_locked_row = True
            st.rerun()

    return selected, is_locked_row

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
    _inject_css()

    # ✅ ONLY IMAGES
    raw_photo_urls = getattr(ctx, "all_photo_urls", []) or []
    photo_labels = getattr(ctx, "photo_label_by_url", {}) or {}
    photo_urls = _only_images(raw_photo_urls)

    # Audio discovery
    audio_url_list, audio_label_by_url, audio_source_msg = _discover_audio(ctx)
    # =======================
    # ✅ AUDIO DEBUG TEST (TEMP)
    # =======================


    card_open("Observations", variant="lg-variant-green")

    comps: List[Dict[str, Any]] = st.session_state[SS_OBS]

    topA, topB, topC = st.columns([0.40, 0.30, 0.30], gap="small")
    with topA:
        show_photo_picker = st.toggle("Pick photos with preview", value=True, key=_k("show_picker"))
    with topB:
        if st.button("Clear all", use_container_width=True, key=_k("clear_all")):
            st.session_state[SS_OBS] = []
            st.session_state[SS_LAST_ADDED_COMP] = None
            comps = st.session_state[SS_OBS]
            st.rerun()
    with topC:
        st.button("➕ Add component", use_container_width=True, key=_k("add_comp_top"), on_click=_add_component)

    if not comps:
        status_card("No components yet", "Use **Add component** to start.", level="warning")

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

            st.divider()

            observations: List[Dict[str, Any]] = comp.get("observations") or []
            if not observations:
                observations = [_ensure_obs_schema({})]

            for oi in range(len(observations)):
                it = _ensure_obs_schema(observations[oi])

                raw_title = _obs_title_raw(it)
                numbered = _numbered_title(SECTION_NO, global_obs_idx, raw_title) if raw_title else ""
                header_title = numbered if numbered else f"Observation {oi + 1}"

                st.markdown("<div class='t6-obs-box'>", unsafe_allow_html=True)

                hdr = st.columns([3, 1], gap="small")
                with hdr[0]:
                    st.markdown(f"**{header_title}**")

                # =======================
                # Audio (GUARANTEED)
                # =======================
                # =======================
                # ✅ Audio (PLAY BY URL)
                # =======================
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
                            audio_url = it["audio_url"]

                            # ✅ IMPORTANT: play by URL in browser (no download in Streamlit server)
                            st.audio(audio_url, format=_guess_audio_mime(audio_url))

                            # Optional: show link
                            st.markdown(
                                f"<a href='{audio_url}' target='_blank' style='font-size:12px; opacity:0.85;'>Open audio in new tab</a>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.caption("None")
                else:
                    it["audio_url"] = ""
                    st.info(audio_source_msg or "No audio links found for this TPM_ID row.")

                st.divider()

                # =======================
                # Title
                # =======================
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
                        it["title_selected"] = st.selectbox(
                            "Select title", options=opts, index=idx, key=_k("title_sel", ci, oi)
                        )
                        it["title_custom"] = ""
                    else:
                        it["title_custom"] = st.text_input(
                            "Custom title", value=_s(it.get("title_custom")), key=_k("title_custom", ci, oi)
                        )
                        it["title_selected"] = ""

                title_final = _obs_title_raw(it)

                # =======================
                # Photos (Step4-like)
                # =======================
                if not photo_urls:
                    st.info("No image/photo URLs are available for this record.")
                    it["photos"] = []
                else:
                    if not title_final:
                        st.warning("Select or enter a title to enable photo selection.")
                        selected_urls: List[str] = []
                        it["photo_picker_locked"] = False
                        it["photos"] = []
                    else:
                        prev_selected = [
                            p.get("url") for p in (it.get("photos") or [])
                            if isinstance(p, dict) and p.get("url") in photo_urls
                        ]
                        prev_selected = [u for u in photo_urls if u in set(prev_selected)]  # stable order

                        if show_photo_picker:
                            st.markdown("**Photos**")

                            selected_urls, locked_now = _render_photo_picker_step4_style(
                                urls=photo_urls,
                                labels=photo_labels,
                                selected_urls=prev_selected,
                                fetch_image=fetch_image,
                                locked_flag=bool(it.get("photo_picker_locked")),
                                scope_key=f"c{ci}.o{oi}",
                            )
                            it["photo_picker_locked"] = bool(locked_now)

                        else:
                            # fallback multiselect (still supports Done lock)
                            selected_urls = st.multiselect(
                                "Select photos for this observation",
                                options=photo_urls,
                                default=prev_selected,
                                format_func=lambda u: photo_labels.get(u, u),
                                key=_k("obs_photos", ci, oi),
                            )
                            selected_urls = [u for u in photo_urls if u in set(selected_urls)]
                            if selected_urls:
                                if st.button("✅ Done selecting", use_container_width=True, key=_k("done_sel_ms", ci, oi)):
                                    it["photo_picker_locked"] = True
                                    for u in selected_urls:
                                        _ensure_full_bytes_selected(u, fetch_image=fetch_image)
                                    st.rerun()
                            else:
                                it["photo_picker_locked"] = False

                        # ensure thumbs for selected (for below preview + per-photo notes)
                        for u in selected_urls[:PREFETCH_LIMIT]:
                            _fetch_thumb_only(u, fetch_image=fetch_image)

                        it["photos"] = _normalize_photos(selected_urls, it.get("photos") or [])

                        if it["photos"]:
                            st.markdown("**Observation for each selected photo**")
                            thumbs: Dict[str, bytes] = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}

                            for pj, ph in enumerate(it["photos"]):
                                u = _s(ph.get("url"))
                                lab = photo_labels.get(u, u)

                                colA, colB = st.columns([1, 2], gap="small")
                                with colA:
                                    tb = thumbs.get(u)
                                    if tb:
                                        st.markdown(_thumb_html(tb, lab), unsafe_allow_html=True)
                                    else:
                                        st.caption(lab)
                                        st.caption("Preview not available.")
                                with colB:
                                    ph["text"] = st.text_area(
                                        "Observation",
                                        value=_s(ph.get("text")),
                                        height=90,
                                        key=_k("photo_obs", ci, oi, pj),
                                        placeholder="Write observation for this photo...",
                                    )

                st.markdown("</div>", unsafe_allow_html=True)  # t6-obs-box end

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

    st.divider()
    card_close()
    return total_valid > 0
