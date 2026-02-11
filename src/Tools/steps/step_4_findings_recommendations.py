from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Callable
from urllib.request import urlopen, Request

import streamlit as st
from PIL import Image, ImageEnhance, ImageOps

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card


# =============================================================================
# OPTIONAL: Paint-like editor (if installed)
#   pip install streamlit-drawable-canvas
# =============================================================================
try:
    from streamlit_drawable_canvas import st_canvas  # type: ignore

    _HAS_CANVAS = True
except Exception:
    st_canvas = None
    _HAS_CANVAS = False


# =============================================================================
# URL filter (images only)
# =============================================================================
IMG_EXT = re.compile(r"\.(jpg|jpeg|png|webp|bmp|tiff)(\?|#|$)", re.I)
_AUD_URL_RE = re.compile(r"\.(mp3|wav|m4a|aac|ogg|opus|flac)(\?|#|$)", re.I)


def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _only_images(urls: List[str]) -> List[str]:
    out: List[str] = []
    for u in urls or []:
        u = _s(u)
        if not u:
            continue
        if IMG_EXT.search(u) or ("googleusercontent.com" in u) or ("lh3.googleusercontent.com" in u):
            out.append(u)
    return list(dict.fromkeys(out))


# =============================================================================
# Session keys
# =============================================================================
SS_OBS = "tool6_obs_components"                  # from Step 3
SS_FIND = "tool6_findings_components"            # Step 4 UI storage
SS_FINAL = "tool6_component_observations_final"  # merged output for DOCX
SS_LOCK = "tool6_report_locked"                  # lock flag (global)
SS_FINAL_LOCKED = "tool6_s4_final_locked"

SS_PHOTO_BYTES = "photo_bytes"                   # full bytes (DOCX + preview) — only selected
SS_PHOTO_THUMBS = "photo_thumbs"                 # thumb bytes cache (fast UI)

SS_ROW_PICK_LOCK = "tool6_s4_row_pick_locked"    # dict: {scope_key: bool}
SS_ROW_PICK_PAGE = "tool6_s4_row_pick_page"      # dict: {scope_key: int}
SS_ROW_PICK_SEARCH = "tool6_s4_row_pick_search"  # dict: {scope_key: str}

SS_IMG_CACHE = "tool6_s4_img_cache"              # {url: {"ts": float, "ok": bool, "bytes": b, "msg": str}}
SS_IMG_CACHE_CFG = "tool6_s4_img_cache_cfg"

SS_AUDIO_BYTES = "tool6_s4_audio_bytes"          # {url: {"ts": float, "ok": bool, "bytes": b, "mime": str}}

# Edited/Annotated image bytes (printed in report)
SS_PHOTO_ANNOTATED = "tool6_s4_photo_annotated"  # {url: png_bytes}

# Autosave throttling per image
SS_ANN_META = "tool6_s4_ann_meta"                # {url: {"hash": str, "ts": float}}


# =============================================================================
# Google Sheet Audio Source (CSV export)
# =============================================================================
AUDIO_SHEET_ID = "1XxWP-d3lIV4vSxjp-8fo-u9JW0QvsOBjbFkl2mQqApc"
AUDIO_GID = "845246438"
AUDIO_TPM_COL = "TPM ID"


# =============================================================================
# Performance constants
# =============================================================================
GRID_COLS = 2
THUMB_BOX = 200
PER_PAGE = 12

# Hover HD (cards)
HOVER_HD_MAXPX = 1920
HOVER_HD_QUALITY = 88
HOVER_HD_BUDGET = 18

# TTL cache
IMG_TTL_OK = 20 * 60
IMG_TTL_FAIL = 90
IMG_CACHE_MAX_ITEMS = 700
IMG_MAX_MB = 25

AUDIO_TTL_OK = 20 * 60
AUDIO_TTL_FAIL = 90
AUDIO_MAX_MB = 40

# Editor output (printable, not huge)
ANNOT_MAXPX = 2600

# Editor UI rendering width (keeps UI fast but still HD preview separately)
EDITOR_CANVAS_MAX_W = 1100

# Autosave throttle (seconds)
ANN_AUTOSAVE_MIN_INTERVAL = 0.35


# =============================================================================
# Key helper
# =============================================================================
def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()
    return f"t6.s4.{h}"


# =============================================================================
# CSS (fixed look across reruns)
# =============================================================================
def _inject_css() -> None:
    st.markdown(
        """
<style>
  [data-testid="stVerticalBlock"] { gap: 0.70rem; }

  .t6-card {
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 12px;
    overflow: hidden;
    background: rgba(255,255,255,0.02);
  }

  .t6-imgbox {
    width: 100%;
    aspect-ratio: 1 / 1;
    background: rgba(0,0,0,0.08);
    display: grid;
    place-items: center;
    position: relative;
    overflow: hidden;
  }

  .t6-imgbox img.t6-thumb {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display:block;
    transition: transform 160ms ease, opacity 120ms ease;
    transform: scale(1.0);
    opacity: 1;
  }

  .t6-imgbox img.t6-hd {
    position:absolute;
    inset:0;
    width:100%;
    height:100%;
    object-fit:contain;
    display:block;
    opacity:0;
    transform: scale(1.05);
    transition: opacity 120ms ease, transform 160ms ease;
    will-change: transform, opacity;
  }

  .t6-card:hover .t6-imgbox img.t6-thumb {
    transform: scale(1.08);
    opacity: 0.08;
  }

  .t6-card:hover .t6-imgbox img.t6-hd {
    opacity: 1;
    transform: scale(1.14);
  }

  .t6-cap {
    padding: 8px 10px 0 10px;
    font-size: 11px;
    opacity: .86;
    line-height: 1.2;
    text-align: right;
    min-height: 28px;
    word-break: break-word;
  }

  .t6-actions {
    display:flex;
    gap: 8px;
    padding: 10px 10px 12px 10px;
  }

  .t6-box {
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px;
    padding: 14px;
    background: rgba(255,255,255,0.02);
    margin: 10px 0 12px 0;
  }

  .t6-muted {
    opacity: .75;
    font-size: 12px;
  }

  .t6-editor-box {
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 14px;
    padding: 12px;
    background: rgba(255,255,255,0.02);
    margin-top: 10px;
  }

  .t6-sticky {
    position: sticky;
    bottom: 0;
    z-index: 50;
    padding: 10px 0 0 0;
    backdrop-filter: blur(8px);
  }

  .t6-sticky-inner {
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(15,15,18,0.60);
    border-radius: 14px;
    padding: 10px;
  }
</style>
""",
        unsafe_allow_html=True,
    )


# =============================================================================
# State init
# =============================================================================
def _ensure_state() -> None:
    ss = st.session_state

    ss.setdefault(SS_FIND, [])
    ss.setdefault(SS_FINAL, [])
    ss.setdefault(SS_LOCK, False)
    ss.setdefault(SS_FINAL_LOCKED, False)

    ss.setdefault(SS_PHOTO_BYTES, {})
    ss.setdefault(SS_PHOTO_THUMBS, {})
    ss.setdefault(SS_PHOTO_ANNOTATED, {})
    ss.setdefault(SS_ANN_META, {})

    ss.setdefault(SS_ROW_PICK_LOCK, {})
    ss.setdefault(SS_ROW_PICK_PAGE, {})
    ss.setdefault(SS_ROW_PICK_SEARCH, {})

    ss.setdefault(SS_IMG_CACHE, {})
    ss.setdefault(
        SS_IMG_CACHE_CFG,
        {"ttl_ok": IMG_TTL_OK, "ttl_fail": IMG_TTL_FAIL, "max_items": IMG_CACHE_MAX_ITEMS, "max_mb": IMG_MAX_MB},
    )

    ss.setdefault(SS_AUDIO_BYTES, {})

    if not isinstance(ss[SS_FIND], list):
        ss[SS_FIND] = []
    if not isinstance(ss[SS_PHOTO_BYTES], dict):
        ss[SS_PHOTO_BYTES] = {}
    if not isinstance(ss[SS_PHOTO_THUMBS], dict):
        ss[SS_PHOTO_THUMBS] = {}
    if not isinstance(ss[SS_PHOTO_ANNOTATED], dict):
        ss[SS_PHOTO_ANNOTATED] = {}
    if not isinstance(ss[SS_ANN_META], dict):
        ss[SS_ANN_META] = {}
    if not isinstance(ss[SS_ROW_PICK_LOCK], dict):
        ss[SS_ROW_PICK_LOCK] = {}
    if not isinstance(ss[SS_ROW_PICK_PAGE], dict):
        ss[SS_ROW_PICK_PAGE] = {}
    if not isinstance(ss[SS_ROW_PICK_SEARCH], dict):
        ss[SS_ROW_PICK_SEARCH] = {}
    if not isinstance(ss[SS_IMG_CACHE], dict):
        ss[SS_IMG_CACHE] = {}
    if not isinstance(ss[SS_AUDIO_BYTES], dict):
        ss[SS_AUDIO_BYTES] = {}


def _is_locked() -> bool:
    return bool(st.session_state.get(SS_FINAL_LOCKED, False)) or bool(st.session_state.get(SS_LOCK, False))


# =============================================================================
# Schemas
# =============================================================================
def _ensure_comp(c: Dict[str, Any]) -> Dict[str, Any]:
    c.setdefault("comp_index", 0)
    c.setdefault("obs_blocks", [])
    return c


def _ensure_obs_block(b: Dict[str, Any]) -> Dict[str, Any]:
    b.setdefault("obs_index", 0)
    b.setdefault("obs_title", "")
    b.setdefault("findings", [])
    b.setdefault("recommendations", [])
    b.setdefault("audio_url", "")
    return b


def _ensure_finding_row(r: Dict[str, Any]) -> Dict[str, Any]:
    r.setdefault("finding", "")
    r.setdefault("Compliance", "")
    r.setdefault("photo", "")     # single photo
    r.setdefault("photos", [])    # legacy
    return r


def _obs_number(comp_index: int, obs_index: int) -> str:
    return f"5.{comp_index + 1}.{obs_index + 1}"


# =============================================================================
# TTL fetch_image cache (critical)
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
        img = Image.open(io.BytesIO(b))
        img = ImageOps.exif_transpose(img).convert("RGB")
        img = ImageEnhance.Contrast(img).enhance(0.95)
        img = ImageEnhance.Brightness(img).enhance(0.97)
        img.thumbnail((box, box), Image.Resampling.LANCZOS)

        bg = Image.new("RGB", (box, box), (32, 32, 36))
        w, h = img.size
        bg.paste(img, ((box - w) // 2, (box - h) // 2))

        out = io.BytesIO()
        bg.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _make_hover_hd(b: bytes, *, max_px: int = HOVER_HD_MAXPX, quality: int = HOVER_HD_QUALITY) -> Optional[bytes]:
    try:
        img = Image.open(io.BytesIO(b))
        img = ImageOps.exif_transpose(img).convert("RGB")

        w, h = img.size
        m = max(w, h)
        if m > max_px:
            scale = max_px / float(m)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return None


@st.cache_data(show_spinner=False, max_entries=8192)
def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def _card_html(thumb: Optional[bytes], hd: Optional[bytes], caption: str) -> str:
    cap = _s(caption)

    if thumb:
        thumb_tag = f"<img class='t6-thumb' loading='lazy' src='data:image/jpeg;base64,{_b64(thumb)}'/>"
    else:
        thumb_tag = "<div class='t6-muted'>No preview</div>"

    hd_tag = f"<img class='t6-hd' loading='lazy' src='data:image/jpeg;base64,{_b64(hd)}'/>" if hd else ""

    return (
        f"<div class='t6-card'>"
        f"  <div class='t6-imgbox'>{thumb_tag}{hd_tag}</div>"
        f"  <div class='t6-cap'>{cap}</div>"
        f"</div>"
    )


def _thumb_and_hd(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
    want_hd: bool,
) -> Tuple[Optional[bytes], Optional[bytes]]:
    ss = st.session_state
    thumbs: Dict[str, bytes] = ss.get(SS_PHOTO_THUMBS, {}) or {}
    th = thumbs.get(url)
    hd: Optional[bytes] = None

    if (not th) or want_hd:
        ok, b, _ = _fetch_image_cached(url, fetch_image=fetch_image)
        if ok and b:
            if not th:
                th = _make_thumb_contain(b)
                if th:
                    thumbs[url] = th
                    ss[SS_PHOTO_THUMBS] = thumbs
            if want_hd:
                hd = _make_hover_hd(b)

    return th, hd


def _ensure_full_bytes_selected(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    url = _s(url)
    if not url:
        return
    ss = st.session_state
    cache: Dict[str, bytes] = ss.get(SS_PHOTO_BYTES, {}) or {}
    if url in cache and cache[url]:
        return
    ok, b, _ = _fetch_image_cached(url, fetch_image=fetch_image)
    if ok and b:
        cache[url] = b
        ss[SS_PHOTO_BYTES] = cache


# =============================================================================
# Audio: cached download
# =============================================================================
def _guess_audio_mime(url: str, fallback: str = "audio/aac") -> str:
    u = _s(url).lower()
    if ".mp3" in u:
        return "audio/mpeg"
    if ".wav" in u:
        return "audio/wav"
    if ".m4a" in u:
        return "audio/mp4"
    if ".aac" in u:
        return "audio/aac"
    if ".ogg" in u:
        return "audio/ogg"
    if ".opus" in u:
        return "audio/opus"
    if ".flac" in u:
        return "audio/flac"
    return fallback


def _download_bytes_urlopen(url: str, timeout: int = 20, max_mb: int = AUDIO_MAX_MB) -> Tuple[bool, Optional[bytes], str]:
    url = _s(url)
    if not url:
        return False, None, "Empty URL"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
        with urlopen(req, timeout=timeout) as resp:
            clen = resp.headers.get("Content-Length")
            if clen:
                try:
                    if int(clen) > max_mb * 1024 * 1024:
                        return False, None, f"Audio too large (> {max_mb}MB)"
                except Exception:
                    pass
            data = resp.read()
            if not data:
                return False, None, "Downloaded 0 bytes"
            if len(data) > max_mb * 1024 * 1024:
                return False, None, f"Audio too large (> {max_mb}MB)"
            return True, data, "OK"
    except Exception as e:
        return False, None, f"Download failed: {e}"


def _audio_bytes_cached(
    url: str,
    *,
    fetch_audio: Optional[Callable[[str], Tuple[bool, Optional[bytes], str, str]]],
) -> Tuple[Optional[bytes], str]:
    url = _s(url)
    if not url:
        return None, ""

    ss = st.session_state
    cache: Dict[str, Dict[str, Any]] = ss.get(SS_AUDIO_BYTES, {}) or {}
    now = time.time()

    hit = cache.get(url)
    if isinstance(hit, dict):
        ts = float(hit.get("ts") or 0.0)
        ok = bool(hit.get("ok"))
        age = now - ts
        if ok and age < AUDIO_TTL_OK:
            return hit.get("bytes"), _s(hit.get("mime"))
        if (not ok) and age < AUDIO_TTL_FAIL:
            return None, _s(hit.get("mime")) or _guess_audio_mime(url)

    if fetch_audio is not None:
        try:
            ok, b, _msg, mime = fetch_audio(url)
            if ok and b:
                mime_clean = (_s(mime).split(";")[0].strip() or _guess_audio_mime(url))
                cache[url] = {"ts": now, "ok": True, "bytes": b, "mime": mime_clean}
                ss[SS_AUDIO_BYTES] = cache
                return b, mime_clean
        except Exception:
            pass

    ok2, b2, _msg2 = _download_bytes_urlopen(url, timeout=20, max_mb=AUDIO_MAX_MB)
    mime2 = _guess_audio_mime(url)
    cache[url] = {"ts": now, "ok": ok2, "bytes": (b2 if ok2 else None), "mime": mime2}
    ss[SS_AUDIO_BYTES] = cache
    return (b2 if ok2 else None), mime2


@st.cache_data(ttl=120, show_spinner=False)
def _fetch_audio_sheet_rows_csv() -> List[Dict[str, str]]:
    # lightweight CSV fetch
    import pandas as pd

    csv_url = f"https://docs.google.com/spreadsheets/d/{AUDIO_SHEET_ID}/export?format=csv&gid={AUDIO_GID}"
    df = pd.read_csv(csv_url, dtype=str).fillna("")
    return df.to_dict(orient="records")


def _audios_for_tpm_id(tpm_id: str) -> List[str]:
    tpm_id = _s(tpm_id)
    if not tpm_id:
        return []
    try:
        rows = _fetch_audio_sheet_rows_csv()
    except Exception:
        return []

    hit: Optional[Dict[str, str]] = None
    for r in rows:
        if _s(r.get(AUDIO_TPM_COL)) == tpm_id:
            hit = r
            break
    if not hit:
        return []

    out: List[str] = []
    for k, v in hit.items():
        kk = _s(k).lower()
        vv = _s(v)
        if not vv:
            continue
        if "audio" in kk or kk.startswith("aud"):
            out.append(vv)

    seen = set()
    dedup: List[str] = []
    for u in out:
        if u in seen:
            continue
        seen.add(u)
        dedup.append(u)
    return dedup


@st.fragment
def _audio_playlist_block(
    *,
    audio_urls: List[str],
    fetch_audio: Optional[Callable[[str], Tuple[bool, Optional[bytes], str, str]]],
    blk: Dict[str, Any],
    locked: bool,
    scope_key: str,
) -> None:
    if not audio_urls:
        blk["audio_url"] = ""
        st.info("No audios available for this TPM ID.")
        return

    cur = _s(blk.get("audio_url"))
    opts = [""] + audio_urls
    idx = opts.index(cur) if cur in opts else 0

    col1, col2 = st.columns([2.3, 1.0], gap="small")
    with col1:
        blk["audio_url"] = st.selectbox(
            "Audio playlist",
            options=opts,
            index=idx,
            format_func=lambda u: "Select audio..." if not u else u.split("/")[-1],
            key=_key("audio_sel", scope_key),
            disabled=locked,
        )
    with col2:
        st.caption("Preview")
        if blk["audio_url"]:
            audio_bytes, mime = _audio_bytes_cached(blk["audio_url"], fetch_audio=fetch_audio)
            if audio_bytes:
                st.audio(audio_bytes, format=mime)
            else:
                st.audio(blk["audio_url"], format=_guess_audio_mime(blk["audio_url"]))
        else:
            st.caption("None selected")


# =============================================================================
# Helpers: prevent photo reuse within same observation block
# =============================================================================
def _used_urls_in_block(block: Dict[str, Any]) -> set:
    used = set()
    for rr in (block.get("findings") or []):
        if isinstance(rr, dict):
            u = _s(rr.get("photo"))
            if u:
                used.add(u)
    return used


def _label(labels: Dict[str, str], url: str) -> str:
    return _s(labels.get(url, url))


# =============================================================================
# Painter-like editor (AUTO-APPLY; no Save button)
# =============================================================================
def _to_printable_png(b: bytes, *, max_px: int = ANNOT_MAXPX) -> bytes:
    img = Image.open(io.BytesIO(b))
    img = ImageOps.exif_transpose(img).convert("RGBA")
    w, h = img.size
    m = max(w, h)
    if m > max_px:
        scale = max_px / float(m)
        img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _hash_bytes(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def _autosave_annotated(url: str, merged_png: bytes) -> None:
    """
    Fast autosave with throttle + content hash.
    """
    ss = st.session_state
    url = _s(url)
    if not url:
        return

    ann: Dict[str, bytes] = ss.get(SS_PHOTO_ANNOTATED, {}) or {}
    meta: Dict[str, Dict[str, Any]] = ss.get(SS_ANN_META, {}) or {}

    now = time.time()
    last = meta.get(url) or {}
    last_ts = float(last.get("ts") or 0.0)
    if (now - last_ts) < ANN_AUTOSAVE_MIN_INTERVAL:
        return

    # Normalize once to printable size, then hash
    printable = _to_printable_png(merged_png)
    h = _hash_bytes(printable)

    if _s(last.get("hash")) == h:
        meta[url] = {"hash": h, "ts": now}
        ss[SS_ANN_META] = meta
        return

    ann[url] = printable
    meta[url] = {"hash": h, "ts": now}
    ss[SS_PHOTO_ANNOTATED] = ann
    ss[SS_ANN_META] = meta


@st.fragment
def _editor_block(
    *,
    url: str,
    labels: Dict[str, str],
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
    locked: bool,
    scope_key: str,
) -> None:
    url = _s(url)
    if not url:
        return

    ss = st.session_state
    annotated: Dict[str, bytes] = ss.get(SS_PHOTO_ANNOTATED, {}) or {}

    _ensure_full_bytes_selected(url, fetch_image=fetch_image)
    pb: Dict[str, bytes] = ss.get(SS_PHOTO_BYTES, {}) or {}
    src = pb.get(url)
    if not src:
        st.info("Image bytes unavailable.")
        return

    st.markdown("<div class='t6-editor-box'>", unsafe_allow_html=True)
    st.markdown(f"**Edit photo (Paint-like)** — {_label(labels, url)}")

    # FULL-HD preview (always, after selection)
    # Uses annotated if exists, else original
    preview_bytes = annotated.get(url) or src
    st.image(preview_bytes, use_container_width=True, caption="Full HD preview (prints exactly)")

    if locked:
        st.caption("Report is locked. Editing disabled.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Base image for canvas: use annotated if exists else original (so edits continue)
    base_bytes = annotated.get(url) or src

    if _HAS_CANVAS and st_canvas is not None:
        # Prepare base image for fast interactive canvas
        img = Image.open(io.BytesIO(base_bytes))
        img = ImageOps.exif_transpose(img).convert("RGBA")

        w, h = img.size
        if w > EDITOR_CANVAS_MAX_W:
            scale = EDITOR_CANVAS_MAX_W / float(w)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

        # Toolbar
        t1, t2, t3, t4 = st.columns([1.1, 1.0, 1.0, 1.3], gap="small")
        with t1:
            mode = st.selectbox(
                "Tool",
                ["freedraw", "line", "rect", "circle", "transform"],
                index=0,
                key=_key("ed_tool", scope_key),
            )
        with t2:
            stroke = st.slider("Stroke", 1, 20, 3, key=_key("ed_stroke", scope_key))
        with t3:
            fill = st.toggle("Fill", value=False, key=_key("ed_fill", scope_key))
        with t4:
            if st.button("Reset edits", use_container_width=True, key=_key("ed_reset", scope_key)):
                annotated.pop(url, None)
                ss[SS_PHOTO_ANNOTATED] = annotated
                ss[SS_ANN_META] = ss.get(SS_ANN_META, {}) or {}
                st.toast("Edits reset", icon="🧽")
                st.rerun()

        # Canvas
        canvas = st_canvas(
            fill_color="rgba(255, 0, 0, 0.0)" if not fill else "rgba(255, 0, 0, 0.18)",
            stroke_width=int(stroke),
            stroke_color="rgba(255, 0, 0, 0.85)",
            background_color="rgba(0, 0, 0, 0)",
            background_image=img,
            update_streamlit=True,
            height=img.size[1],
            width=img.size[0],
            drawing_mode=mode,
            key=_key("canvas", scope_key),
        )

        # AUTO-APPLY (no Save button):
        # When canvas updates, merge background + overlay and autosave.
        try:
            if canvas.image_data is not None:
                overlay = Image.fromarray(canvas.image_data.astype("uint8"), mode="RGBA")
                merged = Image.alpha_composite(img.convert("RGBA"), overlay.convert("RGBA"))
                out = io.BytesIO()
                merged.save(out, format="PNG", optimize=True)
                _autosave_annotated(url, out.getvalue())
        except Exception:
            # keep UI stable (no hard error)
            pass

        st.caption("Edits apply automatically (no Save). The preview above updates on rerun.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Fallback light editor (also AUTO-APPLY)
    st.caption("Canvas editor not available. Using auto light-editor (rotate/brightness/contrast).")

    def _apply_light_now() -> None:
        rot = int(st.session_state.get(_key("rot", scope_key)) or 0)
        br = float(st.session_state.get(_key("br", scope_key)) or 1.0)
        ct = float(st.session_state.get(_key("ct", scope_key)) or 1.0)

        img2 = Image.open(io.BytesIO(src))
        img2 = ImageOps.exif_transpose(img2).convert("RGB")
        if rot:
            img2 = img2.rotate(rot, expand=True)
        img2 = ImageEnhance.Brightness(img2).enhance(br)
        img2 = ImageEnhance.Contrast(img2).enhance(ct)
        out2 = io.BytesIO()
        img2.save(out2, format="PNG", optimize=True)
        _autosave_annotated(url, out2.getvalue())

    colL, colR = st.columns([1, 1], gap="large")
    with colL:
        st.selectbox("Rotate", [0, 90, 180, 270], index=0, key=_key("rot", scope_key), on_change=_apply_light_now)
        st.slider("Brightness", 0.6, 1.4, 1.0, 0.02, key=_key("br", scope_key), on_change=_apply_light_now)
        st.slider("Contrast", 0.6, 1.4, 1.0, 0.02, key=_key("ct", scope_key), on_change=_apply_light_now)

        if st.button("Reset edits", use_container_width=True, key=_key("reset_light", scope_key)):
            annotated.pop(url, None)
            ss[SS_PHOTO_ANNOTATED] = annotated
            st.toast("Edits reset", icon="🧽")
            st.rerun()

    with colR:
        preview2 = (st.session_state.get(SS_PHOTO_ANNOTATED, {}) or {}).get(url) or src
        st.image(preview2, caption="Preview (prints)", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# Photo picker (single photo per finding)
# - Select => immediately lock + hide others
# - After selection, editor shows FULL HD preview
# =============================================================================
@st.fragment
def _render_photo_picker_single(
    *,
    all_urls: List[str],
    labels: Dict[str, str],
    rr: Dict[str, Any],
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
    locked: bool,
    scope_key: str,
    used_urls: set,
) -> Dict[str, Any]:
    rr = _ensure_finding_row(rr)
    ss = st.session_state

    row_locks: Dict[str, bool] = ss.get(SS_ROW_PICK_LOCK, {}) or {}
    is_locked_row = bool(row_locks.get(scope_key, False))

    selected = _s(rr.get("photo"))
    if selected and selected not in all_urls:
        selected = ""
        rr["photo"] = ""

    urls = [u for u in all_urls if (u == selected) or (u not in used_urls)]

    pages: Dict[str, int] = ss.get(SS_ROW_PICK_PAGE, {}) or {}
    searches: Dict[str, str] = ss.get(SS_ROW_PICK_SEARCH, {}) or {}

    q = _s(searches.get(scope_key, ""))
    page = int(pages.get(scope_key, 1) or 1)

    h1, h2, h3 = st.columns([1.0, 1.2, 1.0], gap="small")
    with h1:
        st.caption(f"Available: {len(urls)}")
    with h2:
        st.caption(f"Selected: {'Yes' if bool(selected) else 'No'}")
    with h3:
        if is_locked_row and selected:
            if st.button("Edit selection", use_container_width=True, key=_key("unlock", scope_key), disabled=locked):
                row_locks[scope_key] = False
                ss[SS_ROW_PICK_LOCK] = row_locks
                st.rerun()

    # Locked: show selected only (and make sure we have FULL bytes)
    if is_locked_row and selected:
        _ensure_full_bytes_selected(selected, fetch_image=fetch_image)
        th, hd = _thumb_and_hd(selected, fetch_image=fetch_image, want_hd=True)
        st.markdown(_card_html(th, hd, _label(labels, selected)), unsafe_allow_html=True)
        rr["photos"] = [selected]
        return rr

    # Search + pagination
    cS, cP, cC = st.columns([2.0, 1.0, 1.0], gap="small")
    with cS:
        q2 = st.text_input(
            "Search photos",
            value=q,
            placeholder="Search…",
            key=_key("search", scope_key),
            label_visibility="collapsed",
            disabled=locked,
        )
    with cC:
        if st.button("Clear", use_container_width=True, key=_key("clear", scope_key), disabled=locked):
            q2 = ""
            page = 1

    q2 = _s(q2).lower()
    searches[scope_key] = q2
    ss[SS_ROW_PICK_SEARCH] = searches

    filtered = [u for u in urls if (q2 in _label(labels, u).lower())] if q2 else list(urls)
    if not filtered:
        st.info("No images match your search (or all are used in other findings).")
        rr["photos"] = []
        return rr

    total = len(filtered)
    max_page = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = max(1, min(page, max_page))

    with cP:
        page2 = st.number_input(
            "Page",
            min_value=1,
            max_value=max_page,
            value=int(page),
            step=1,
            key=_key("page", scope_key),
            label_visibility="collapsed",
            disabled=locked,
        )
        page = int(page2)

    pages[scope_key] = page
    ss[SS_ROW_PICK_PAGE] = pages

    start = (page - 1) * PER_PAGE
    chunk = filtered[start:start + PER_PAGE]

    hd_set = set(chunk[: min(HOVER_HD_BUDGET, len(chunk))])

    cols = GRID_COLS
    for i in range(0, len(chunk), cols):
        row = chunk[i:i + cols]
        columns = st.columns(cols, gap="small")

        for col, url in zip(columns, row + [None] * (cols - len(row))):
            with col:
                if not url:
                    continue

                want_hd = url in hd_set
                th, hd = _thumb_and_hd(url, fetch_image=fetch_image, want_hd=want_hd)
                st.markdown(_card_html(th, hd, _label(labels, url)), unsafe_allow_html=True)

                st.markdown("<div class='t6-actions'>", unsafe_allow_html=True)
                if st.button("Select", use_container_width=True, key=_key("sel", scope_key, urls.index(url)), disabled=locked):
                    rr["photo"] = url
                    rr["photos"] = [url]
                    _ensure_full_bytes_selected(url, fetch_image=fetch_image)

                    row_locks[scope_key] = True
                    ss[SS_ROW_PICK_LOCK] = row_locks
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

    rr["photos"] = [rr["photo"]] if rr.get("photo") else []
    return rr


# =============================================================================
# Merge to final (includes annotated bytes)
# - IMPORTANT: we store "photo_bytes" in row using annotated if exists, else original.
# =============================================================================
def _merge_to_final() -> List[Dict[str, Any]]:
    obs = st.session_state.get(SS_OBS, []) or []
    find = st.session_state.get(SS_FIND, []) or []
    photo_cache: Dict[str, bytes] = st.session_state.get(SS_PHOTO_BYTES, {}) or {}
    ann_cache: Dict[str, bytes] = st.session_state.get(SS_PHOTO_ANNOTATED, {}) or {}

    final: List[Dict[str, Any]] = []

    for comp_index, comp3 in enumerate(obs):
        comp = {
            "comp_id": _s(comp3.get("comp_id")),
            "title": _s(comp3.get("title")),
            "observations_valid": list(comp3.get("observations_valid") or []),
        }

        comp4: Optional[Dict[str, Any]] = None
        for fc in find:
            try:
                if int(fc.get("comp_index", -1)) == comp_index:
                    comp4 = fc
                    break
            except Exception:
                continue

        blocks = (comp4.get("obs_blocks") or []) if isinstance(comp4, dict) else []
        ov: List[Dict[str, Any]] = comp["observations_valid"] or []

        for blk in blocks:
            blk = _ensure_obs_block(blk)
            try:
                oi = int(blk.get("obs_index", -1))
            except Exception:
                oi = -1
            if oi < 0 or oi >= len(ov):
                continue

            major_table: List[Dict[str, Any]] = []
            for rr in (blk.get("findings") or []):
                rr = _ensure_finding_row(rr)
                finding = _s(rr.get("finding"))
                compliance = _s(rr.get("Compliance"))

                p = _s(rr.get("photo"))
                if not (finding or compliance or p):
                    continue

                # SINGLE photo, but we provide a direct bytes field for the report:
                # annotated wins (paint edits), else original cached
                chosen_bytes = ann_cache.get(p) or photo_cache.get(p)

                major_table.append(
                    {
                        "finding": finding,
                        # keep BOTH keys for backward compatibility with your report code(s)
                        "Compliance": compliance,
                        "compliance": compliance,
                        "photo": p,                     # for report that expects single "photo"
                        "photo_bytes": chosen_bytes,     # for report that supports direct bytes
                    }
                )

            recs = [x for x in (blk.get("recommendations") or []) if _s(x)]

            ov_item = ov[oi]
            ov_item["title"] = _s(blk.get("obs_title")) or _s(ov_item.get("title"))
            ov_item["major_table"] = major_table
            ov_item["recommendations"] = recs
            ov_item["audio_url"] = _s(blk.get("audio_url"))
            ov[oi] = ov_item

        comp["observations_valid"] = ov
        final.append(comp)

    st.session_state[SS_FINAL] = final
    return final


# =============================================================================
# PUBLIC ENTRYPOINT
# =============================================================================
def render_step(
    ctx: Tool6Context,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
    fetch_audio: Optional[Callable[[str], Tuple[bool, Optional[bytes], str, str]]] = None,
) -> bool:
    _ensure_state()
    _inject_css()

    obs = st.session_state.get(SS_OBS, []) or []
    if not obs:
        status_card("Step 3 is empty", "Please complete Step 3 (Observations) first.", level="error")
        return False

    locked = _is_locked()

    # Ensure one Step 4 entry per Step 3 component
    find_list: List[Dict[str, Any]] = st.session_state[SS_FIND]
    if len(find_list) < len(obs):
        for i in range(len(find_list), len(obs)):
            find_list.append(_ensure_comp({"comp_index": i, "obs_blocks": []}))
    find_list = find_list[: len(obs)]
    st.session_state[SS_FIND] = find_list

    # Photos list (stable natural order)
    raw_urls = getattr(ctx, "all_photo_urls", []) or []
    urls_all = _only_images(raw_urls)
    labels = getattr(ctx, "photo_label_by_url", {}) or {}

    # Audio by TPM ID
    tpm_id = _s(getattr(ctx, "tpm_id", "")) or _s(st.session_state.get("tpm_id", ""))
    t1, t2 = st.columns([1.4, 1.0], gap="small")
    with t1:
        tpm_id = st.text_input("TPM ID", value=tpm_id, key=_key("tpm_id"), disabled=locked)
        st.session_state["tpm_id"] = tpm_id
    with t2:
        st.caption("Audio source: Google Sheet (TPM ID row)")

    audio_urls = _audios_for_tpm_id(tpm_id)

    card_open("Findings & Recommendations (Enterprise)", variant="lg-variant-green")

    tools_opts = ["", "Yes", "No", "N/A"]

    for comp_i, comp3 in enumerate(obs):
        comp_title = _s(comp3.get("title")) or f"Component {comp_i + 1}"
        comp_id = _s(comp3.get("comp_id"))
        head = f"{comp_id} — {comp_title}".strip(" —")

        with st.expander(head, expanded=(comp_i == 0)):
            comp4 = _ensure_comp(find_list[comp_i])

            obs_valid: List[Dict[str, Any]] = comp3.get("observations_valid") or []
            if not obs_valid:
                st.info("This component has no observations in Step 3.")
                comp4["obs_blocks"] = []
                find_list[comp_i] = comp4
                continue

            blocks: List[Dict[str, Any]] = comp4.get("obs_blocks") or []
            if len(blocks) < len(obs_valid):
                for j in range(len(blocks), len(obs_valid)):
                    blocks.append(
                        _ensure_obs_block(
                            {
                                "obs_index": j,
                                "obs_title": _s(obs_valid[j].get("title")),
                                "findings": [_ensure_finding_row({})],
                                "recommendations": [""],
                                "audio_url": "",
                            }
                        )
                    )
            blocks = blocks[: len(obs_valid)]

            for j in range(len(obs_valid)):
                blocks[j] = _ensure_obs_block(blocks[j])
                blocks[j]["obs_index"] = j
                blocks[j]["obs_title"] = _s(obs_valid[j].get("title"))

            for obs_i, blk in enumerate(blocks):
                blk = _ensure_obs_block(blk)

                st.markdown("---")
                st.markdown(f"### {_obs_number(comp_i, obs_i)} — {blk['obs_title']}")

                _audio_playlist_block(
                    audio_urls=audio_urls,
                    fetch_audio=fetch_audio,
                    blk=blk,
                    locked=locked,
                    scope_key=f"c{comp_i}.o{obs_i}",
                )

                st.divider()
                st.markdown("**Major findings** (each finding can select exactly ONE photo)")

                rows: List[Dict[str, Any]] = blk.get("findings") or [_ensure_finding_row({})]
                new_rows: List[Dict[str, Any]] = []

                used_in_blk = _used_urls_in_block(blk)

                for r_idx, rr in enumerate(rows):
                    rr = _ensure_finding_row(rr)
                    scope_row = f"c{comp_i}.o{obs_i}.r{r_idx}"

                    cur_sel = _s(rr.get("photo"))
                    used_now = set(used_in_blk)
                    if cur_sel:
                        used_now.discard(cur_sel)

                    st.markdown("<div class='t6-box'>", unsafe_allow_html=True)

                    c1, c2 = st.columns([2.2, 1.0], gap="small")
                    with c1:
                        rr["finding"] = st.text_area(
                            f"Finding #{r_idx + 1}",
                            value=_s(rr.get("finding")),
                            height=90,
                            key=_key("finding", comp_i, obs_i, r_idx),
                            disabled=locked,
                        )
                    with c2:
                        cur_tools = _s(rr.get("Compliance"))
                        idx = tools_opts.index(cur_tools) if cur_tools in tools_opts else 0
                        rr["Compliance"] = st.selectbox(
                            "Compliance",
                            options=tools_opts,
                            index=idx,
                            key=_key("Compliance", comp_i, obs_i, r_idx),
                            disabled=locked,
                        )

                    st.markdown("**Photo picker (Pagination + Lazy + Hover HD)**")

                    rr = _render_photo_picker_single(
                        all_urls=urls_all,
                        labels=labels,
                        rr=rr,
                        fetch_image=fetch_image,
                        locked=locked,
                        scope_key=scope_row,
                        used_urls=used_now,
                    )

                    # When selected: show FULL-HD preview + auto paint editor
                    if _s(rr.get("photo")):
                        _editor_block(
                            url=_s(rr.get("photo")),
                            labels=labels,
                            fetch_image=fetch_image,
                            locked=locked,
                            scope_key=scope_row,
                        )

                    st.markdown("</div>", unsafe_allow_html=True)
                    new_rows.append(rr)

                    if _s(rr.get("photo")):
                        used_in_blk.add(_s(rr.get("photo")))

                btns = st.columns([1, 1], gap="small")
                with btns[0]:
                    if st.button("Add another finding", key=_key("add_row", comp_i, obs_i), use_container_width=True, disabled=locked):
                        new_rows.append(_ensure_finding_row({}))
                        blk["findings"] = new_rows
                        blocks[obs_i] = blk
                        st.rerun()
                with btns[1]:
                    if st.button("Remove last finding", key=_key("rm_row", comp_i, obs_i), use_container_width=True, disabled=locked) and len(new_rows) > 1:
                        new_rows = new_rows[:-1]
                        blk["findings"] = new_rows
                        blocks[obs_i] = blk
                        st.rerun()

                blk["findings"] = new_rows

                st.divider()
                st.markdown("**Recommendations**")

                recs: List[str] = blk.get("recommendations") or [""]
                new_recs: List[str] = []
                for p_idx, txt in enumerate(recs):
                    new_recs.append(
                        st.text_area(
                            f"Recommendation paragraph {p_idx + 1}",
                            value=_s(txt),
                            height=70,
                            key=_key("rec", comp_i, obs_i, p_idx),
                            disabled=locked,
                        )
                    )

                rbtns = st.columns([1, 1], gap="small")
                with rbtns[0]:
                    if st.button("Add recommendation paragraph", key=_key("add_rec", comp_i, obs_i), use_container_width=True, disabled=locked):
                        new_recs.append("")
                        blk["recommendations"] = new_recs
                        blocks[obs_i] = blk
                        st.rerun()
                with rbtns[1]:
                    if st.button("Remove last", key=_key("rm_rec", comp_i, obs_i), use_container_width=True, disabled=locked) and len(new_recs) > 1:
                        new_recs = new_recs[:-1]
                        blk["recommendations"] = new_recs
                        blocks[obs_i] = blk
                        st.rerun()

                blk["recommendations"] = [x for x in new_recs if _s(x)]
                blocks[obs_i] = blk

            comp4["obs_blocks"] = blocks
            find_list[comp_i] = comp4

    st.session_state[SS_FIND] = find_list

    # Merge continuously (cheap) so report is always up-to-date
    _merge_to_final()

    # Sticky lock controls (UI stays the same)
    st.markdown("<div class='t6-sticky'><div class='t6-sticky-inner'>", unsafe_allow_html=True)
    cL, cR = st.columns([1, 1], gap="small")
    with cL:
        if not st.session_state.get(SS_FINAL_LOCKED, False):
            if st.button("🔒 Lock Report (Finalize Step 4)", use_container_width=True, type="primary"):
                st.session_state[SS_FINAL_LOCKED] = True
                st.session_state[SS_LOCK] = True
                st.toast("Report locked", icon="🔒")
                st.rerun()
        else:
            st.success("Report is locked. Editing disabled.")
    with cR:
        if st.session_state.get(SS_FINAL_LOCKED, False):
            if st.button("Unlock (Admin Only)", use_container_width=True):
                st.session_state[SS_FINAL_LOCKED] = False
                st.session_state[SS_LOCK] = False
                st.toast("Unlocked", icon="🔓")
                st.rerun()
    st.markdown("</div></div>", unsafe_allow_html=True)

    card_close()

    # Validation: at least one finding exists
    final = st.session_state.get(SS_FINAL, []) or []
    ok_any = False
    for comp in final:
        for ob in (comp.get("observations_valid") or []):
            mt = ob.get("major_table") or []
            if any(_s(x.get("finding")) for x in mt if isinstance(x, dict)):
                ok_any = True
                break
        if ok_any:
            break

    return ok_any
