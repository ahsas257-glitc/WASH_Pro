from __future__ import annotations

import base64
import hashlib
import io
import json
from typing import Any, Dict, List, Optional, Tuple, Callable

import streamlit as st
from PIL import Image, ImageEnhance

from src.Tools.steps.step_1_cover import ensure_full_image_bytes, render_thumbnail, cache_thumbnail_only
from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card

import re

IMG_EXT = re.compile(r"\.(jpg|jpeg|png|webp|bmp|tiff)(\?|#|$)", re.I)

def _only_images(urls: List[str]) -> List[str]:
    out = []

    for u in urls or []:
        u = _s(u)
        if not u:
            continue

        if IMG_EXT.search(u):
            out.append(u)
            continue

        # Google photos
        if "googleusercontent.com" in u or "lh3.googleusercontent.com" in u:
            out.append(u)

    return list(dict.fromkeys(out))

# =============================================================================
# Session keys
# =============================================================================
SS_OBS = "tool6_obs_components"                  # from Step 3
SS_FIND = "tool6_findings_components"            # Step 4 UI storage
SS_FINAL = "tool6_component_observations_final"  # merged output for DOCX
SS_LOCK = "tool6_report_locked"                  # lock flag

SS_PHOTO_BYTES = "photo_bytes"                   # full bytes cache (DOCX) — only selected
SS_PHOTO_THUMBS = "photo_thumbs"                 # thumb bytes cache (fast UI)
SS_PHOTO_MARKUP_BYTES = "photo_markup_bytes"     # annotated outputs {cache_key: png_bytes}

# NEW: lock selection per finding-row (cover-like)
SS_ROW_PICK_LOCK = "tool6_s4_row_pick_locked"    # dict: {scope_key: bool}


# =============================================================================
# Google Sheet Audio Source (CSV export)
# =============================================================================
AUDIO_SHEET_ID = "1XxWP-d3lIV4vSxjp-8fo-u9JW0QvsOBjbFkl2mQqApc"
AUDIO_GID = "845246438"
AUDIO_TPM_COL = "TPM ID"


# =============================================================================
# UI constants
# =============================================================================
TILE = 120              # small square feel
GRID_COLS = 3           # 3 columns
THUMB_BOX = 220         # thumb canvas for contain mode (quality)


# =============================================================================
# Small utils
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"t6.s4.{h}"


def _sha1_hex(sv: str) -> str:
    return hashlib.sha1(sv.encode("utf-8")).hexdigest()


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


# =============================================================================
# CSS (Cover-like)
# =============================================================================
def _inject_gallery_css() -> None:
    st.markdown(
        f"""
        <style>
          [data-testid="stVerticalBlock"] {{ gap: 0.70rem; }}

          /* RTL grid like cover */
          .t6-grid {{
            direction: rtl;
            display:grid;
            grid-template-columns: repeat({GRID_COLS}, minmax(0, 1fr));
            gap: 10px;
            align-items: start;
          }}

          .t6-card {{
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 12px;
            overflow: hidden;
            background: rgba(255,255,255,0.02);
          }}

          /* show full image (NO crop) */
          .t6-card img {{
            width: 100%;
            height: {TILE}px;
            object-fit: contain;
            background: rgba(0,0,0,0.06);
            display:block;
          }}

          .t6-cap {{
            padding: 6px 8px 0 8px;
            font-size: 11px;
            opacity: .86;
            line-height: 1.2;
            text-align: right;
            min-height: 30px;
            word-break: break-word;
          }}

          .t6-actions {{
            display:flex;
            gap: 6px;
            padding: 6px 8px 8px 8px;
          }}

          .t6-count {{
            font-size: 12px;
            opacity: .82;
          }}

          .t6-box {{
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 14px;
            padding: 14px;
            background: rgba(255,255,255,0.02);
            margin: 10px 0 12px 0;
          }}
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
    ss.setdefault(SS_PHOTO_BYTES, {})
    ss.setdefault(SS_PHOTO_THUMBS, {})
    ss.setdefault(SS_PHOTO_MARKUP_BYTES, {})
    ss.setdefault(SS_ROW_PICK_LOCK, {})

    if not isinstance(ss[SS_FIND], list):
        ss[SS_FIND] = []
    if not isinstance(ss[SS_PHOTO_BYTES], dict):
        ss[SS_PHOTO_BYTES] = {}
    if not isinstance(ss[SS_PHOTO_THUMBS], dict):
        ss[SS_PHOTO_THUMBS] = {}
    if not isinstance(ss[SS_PHOTO_MARKUP_BYTES], dict):
        ss[SS_PHOTO_MARKUP_BYTES] = {}
    if not isinstance(ss[SS_ROW_PICK_LOCK], dict):
        ss[SS_ROW_PICK_LOCK] = {}


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
    b.setdefault("bulk_findings_text", "")
    return b


def _ensure_finding_row(r: Dict[str, Any]) -> Dict[str, Any]:
    r.setdefault("finding", "")
    r.setdefault("Compliance", "")     # exact
    r.setdefault("photo", "")          # legacy single
    r.setdefault("photos", [])         # multi

    r.setdefault("photo_edits", {})    # {url: {brightness, contrast, color}}
    r.setdefault("photo_markups", {})  # {url: canvas.json_data}
    return r


def _is_locked() -> bool:
    return bool(st.session_state.get(SS_LOCK, False))


def _lock_ui_controls() -> None:
    st.session_state[SS_LOCK] = True


def _unlock_ui_controls() -> None:
    st.session_state[SS_LOCK] = False


def _obs_number(comp_index: int, obs_index: int) -> str:
    return f"5.{comp_index + 1}.{obs_index + 1}"


# =============================================================================
# Bulk paste parser
# =============================================================================
def _parse_bulk_findings(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        if "|" in line:
            left, right = [p.strip() for p in line.split("|", 1)]
            if left.lower() in ("yes", "no", "n/a", "na"):
                out.append(
                    {
                        "Compliance": "N/A" if left.lower() in ("n/a", "na") else left.title(),
                        "finding": right,
                        "photo": "",
                        "photos": [],
                        "photo_edits": {},
                        "photo_markups": {},
                    }
                )
                continue

        out.append(
            {
                "Compliance": "",
                "finding": line,
                "photo": "",
                "photos": [],
                "photo_edits": {},
                "photo_markups": {},
            }
        )
    return out


# =============================================================================
# Thumbs: fast, show FULL image (contain), keep quality
# =============================================================================
def _make_thumb_contain(b: bytes, *, box: int = THUMB_BOX, quality: int = 82) -> Optional[bytes]:
    try:
        img = Image.open(io.BytesIO(b)).convert("RGB")

        # Auto contrast fix
        img = ImageEnhance.Contrast(img).enhance(0.95)
        img = ImageEnhance.Brightness(img).enhance(0.97)

        img.thumbnail((box, box), Image.Resampling.LANCZOS)

        bg = Image.new("RGB", (box, box), (32, 32, 36))  # dark neutral

        w, h = img.size
        bg.paste(img, ((box - w)//2, (box - h)//2))

        out = io.BytesIO()
        bg.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()

    except Exception:
        return None



def _thumb_html(thumb_bytes: bytes, caption: str) -> str:
    b64 = base64.b64encode(thumb_bytes).decode("utf-8")
    cap = _s(caption)
    return (
        f"<div class='t6-card'>"
        f"<img src='data:image/jpeg;base64,{b64}'/>"
        f"<div class='t6-cap'>{cap}</div>"
        f"</div>"
    )


def _cache_photo_bytes(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> Optional[bytes]:
    url = _s(url)
    if not url:
        return None

    cache: Dict[str, bytes] = st.session_state.get(SS_PHOTO_BYTES, {}) or {}
    if url in cache and cache[url]:
        return cache[url]

    ok, b, _msg = fetch_image(url)
    if ok and b:
        cache[url] = b
        st.session_state[SS_PHOTO_BYTES] = cache
        return b
    return None


def _cache_thumb_only(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    url = _s(url)
    if not url:
        return

    thumbs: Dict[str, bytes] = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}
    if url in thumbs and thumbs[url]:
        return

    ok, b, _msg = fetch_image(url)
    if ok and b:
        th = _make_thumb_contain(b)
        if th:
            thumbs[url] = th
            st.session_state[SS_PHOTO_THUMBS] = thumbs


def _ensure_full_bytes_selected(
    url: str,
    *,
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
) -> None:
    # full bytes only for selected (DOCX)
    _cache_photo_bytes(url, fetch_image=fetch_image)


def _prefetch_thumbs(urls: List[str], *, fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]], limit: int = 36) -> None:
    urls = [u for u in (urls or []) if _s(u)]
    urls = urls[: max(0, int(limit))]
    thumbs: Dict[str, bytes] = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}
    for u in urls:
        if u in thumbs:
            continue
        _cache_thumb_only(u, fetch_image=fetch_image)


# =============================================================================
# Markup cache
# =============================================================================
def _markup_cache_key(photo_url: str, markup_payload: Dict[str, Any], edit_params: Dict[str, Any]) -> str:
    raw = (
        photo_url
        + "::"
        + json.dumps(markup_payload or {}, ensure_ascii=False, sort_keys=True)
        + "::"
        + json.dumps(edit_params or {}, ensure_ascii=False, sort_keys=True)
    )
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    return f"{photo_url}::mk::{h}"


def _save_annotated_png_bytes(photo_url: str, markup_payload: Dict[str, Any], edit_params: Dict[str, Any], png_bytes: bytes) -> None:
    cache = st.session_state.get(SS_PHOTO_MARKUP_BYTES, {}) or {}
    cache[_markup_cache_key(photo_url, markup_payload, edit_params)] = png_bytes
    st.session_state[SS_PHOTO_MARKUP_BYTES] = cache


def _apply_edits_to_image_bytes(b: bytes, edits: Dict[str, Any]) -> bytes:
    img = Image.open(io.BytesIO(b)).convert("RGB")

    br = float(edits.get("brightness", 1.0))
    ct = float(edits.get("contrast", 1.0))
    cl = float(edits.get("color", 1.0))

    if br != 1.0:
        img = ImageEnhance.Brightness(img).enhance(br)
    if ct != 1.0:
        img = ImageEnhance.Contrast(img).enhance(ct)
    if cl != 1.0:
        img = ImageEnhance.Color(img).enhance(cl)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


# =============================================================================
# Audio CSV (unchanged)
# =============================================================================
@st.cache_data(ttl=120, show_spinner=False)
def _fetch_audio_sheet_rows_csv() -> List[Dict[str, str]]:
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

    dedup: List[str] = []
    seen = set()
    for u in out:
        if u in seen:
            continue
        seen.add(u)
        dedup.append(u)
    return dedup


# =============================================================================
# Merge (unchanged)
# =============================================================================
def _merge_to_final() -> List[Dict[str, Any]]:
    obs = st.session_state.get(SS_OBS, []) or []
    find = st.session_state.get(SS_FIND, []) or []
    photo_cache: Dict[str, bytes] = st.session_state.get(SS_PHOTO_BYTES, {}) or {}
    markup_cache: Dict[str, bytes] = st.session_state.get(SS_PHOTO_MARKUP_BYTES, {}) or {}

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

                photos = rr.get("photos") if isinstance(rr.get("photos"), list) else []
                photos = [_s(x) for x in photos if _s(x)]

                single_photo = _s(rr.get("photo"))
                if single_photo and single_photo not in photos:
                    photos = photos + [single_photo]

                photo_bytes_list: List[Optional[bytes]] = []
                annotated_bytes_list: List[Optional[bytes]] = []

                markups = rr.get("photo_markups") if isinstance(rr.get("photo_markups"), dict) else {}
                edits_map = rr.get("photo_edits") if isinstance(rr.get("photo_edits"), dict) else {}

                for purl in photos:
                    photo_bytes_list.append(photo_cache.get(purl))

                    payload = markups.get(purl) if isinstance(markups.get(purl), dict) else {}
                    edits = edits_map.get(purl) if isinstance(edits_map.get(purl), dict) else {}

                    if payload or edits:
                        key = _markup_cache_key(purl, payload, edits)
                        annotated_bytes_list.append(markup_cache.get(key))
                    else:
                        annotated_bytes_list.append(None)

                if finding or compliance or photos:
                    major_table.append(
                        {
                            "finding": finding,
                            "Compliance": compliance,
                            "photos": photos,
                            "photo_bytes_list": photo_bytes_list,
                            "annotated_photo_bytes_list": annotated_bytes_list,
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
# Photo Picker (Cover-like: Done/Change selection)
# =============================================================================
def _render_photo_picker_and_preview(
    *,
    urls: List[str],
    labels: Dict[str, str],
    rr: Dict[str, Any],
    fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]],
    locked: bool,
    scope_key: str,
) -> Dict[str, Any]:

    rr = _ensure_finding_row(rr)

    # init per-row lock
    pick_locks = st.session_state.setdefault("S4_ROW_LOCKS", {})
    is_locked_row = bool(pick_locks.get(scope_key, False))

    thumbs = st.session_state.setdefault(SS_PHOTO_THUMBS, {})

    def get_label(u: str) -> str:
        return _s(labels.get(u, u))

    # ===============================
    # Selected photos (keep order)
    # ===============================
    selected = rr.get("photos") if isinstance(rr.get("photos"), list) else []
    selected = [_s(x) for x in selected if _s(x)]

    # keep original order from urls
    selected = [u for u in urls if u in set(selected)]
    rr["photos"] = selected

    # ===============================
    # Header (like cover)
    # ===============================
    h1, h2, h3 = st.columns([1, 1, 1])

    with h1:
        st.caption(f"Total: {len(urls)}")

    with h2:
        st.caption(f"Selected: {len(rr['photos'])}")

    with h3:
        if is_locked_row and rr["photos"]:
            if st.button(
                "Change selection",
                key=_key("chg", scope_key),
                use_container_width=True,
                disabled=locked,
            ):
                pick_locks[scope_key] = False
                st.rerun()

    # ===============================
    # Which photos to show
    # ===============================
    if is_locked_row and rr["photos"]:
        show_urls = rr["photos"]
    else:
        show_urls = urls

    # ===============================
    # Preload thumbs (fast)
    # ===============================
    for u in show_urls[:36]:
        if u not in thumbs:
            cache_thumbnail_only(u, fetch_image=fetch_image)

    # ===============================
    # Render grid (3 cols, like cover)
    # ===============================
    cols = 3

    for i in range(0, len(show_urls), cols):
        row = show_urls[i:i + cols]
        columns = st.columns(cols)

        for col, url in zip(columns, row + [None] * (cols - len(row))):

            with col:

                if not url:
                    continue

                # Thumbnail
                if thumb := thumbs.get(url):
                    render_thumbnail(thumb, get_label(url))
                else:
                    st.caption("Preview unavailable")
                    st.caption(get_label(url))

                is_selected = url in rr["photos"]

                # ===============================
                # Buttons
                # ===============================
                if not is_locked_row:

                    if not is_selected:
                        if st.button(
                            "Select",
                            key=_key("sel", scope_key, url),
                            use_container_width=True,
                            disabled=locked,
                        ):
                            rr["photos"].append(url)

                            # reorder
                            rr["photos"] = [x for x in urls if x in set(rr["photos"])]

                            st.rerun()

                    else:
                        if st.button(
                            "Remove",
                            key=_key("rm", scope_key, url),
                            use_container_width=True,
                            disabled=locked,
                        ):
                            rr["photos"] = [x for x in rr["photos"] if x != url]
                            st.rerun()

    # ===============================
    # Done selecting (like cover)
    # ===============================
    if not is_locked_row:

        if st.button(
            "✅ Done selecting",
            use_container_width=True,
            disabled=locked or len(rr["photos"]) == 0,
            key=_key("done", scope_key),
        ):

            # cache full bytes only for selected
            for u in rr["photos"]:
                ensure_full_image_bytes(u, fetch_image=fetch_image)

            pick_locks[scope_key] = True
            st.rerun()

    rr["photo"] = rr["photos"][0] if rr["photos"] else ""

    return rr


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
    _inject_gallery_css()

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

    # Photos list (keep natural order)
    raw_urls = getattr(ctx, "all_photo_urls", []) or []
    urls = _only_images(raw_urls)

    labels = getattr(ctx, "photo_label_by_url", {}) or {}

    # AUDIO (same logic)
    tpm_id = _s(getattr(ctx, "tpm_id", "")) or _s(st.session_state.get("tpm_id", ""))
    aT1, aT2 = st.columns([1.4, 1.0], gap="small")
    with aT1:
        tpm_id = st.text_input("TPM ID", value=tpm_id, key=_key("tpm_id"), disabled=locked)
        st.session_state["tpm_id"] = tpm_id
    with aT2:
        st.caption("Audio source: Google Sheet (TPM ID row)")

    audio_urls = _audios_for_tpm_id(tpm_id)

    if audio_urls:
        st.markdown("### 🎧 Audios (from TPM ID)")
        sel = st.selectbox(
            "Select audio to play",
            options=[""] + audio_urls,
            index=0,
            format_func=lambda u: "Select..." if not u else u,
            key=_key("audio_sel"),
            disabled=locked,
        )
        if sel:
            # best-effort: bytes first
            if fetch_audio is not None:
                ok, b, _msg, mime = fetch_audio(sel)
                if ok and b:
                    st.audio(b, format=(mime or _guess_audio_mime(sel)).split(";")[0])
                else:
                    st.audio(sel, format=_guess_audio_mime(sel))
            else:
                st.audio(sel, format=_guess_audio_mime(sel))
        st.divider()
    else:
        st.info("No audios found for this TPM ID (or sheet not accessible).")
        st.divider()

    tools_opts = ["", "Yes", "No", "N/A"]

    # Render components
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
                                "bulk_findings_text": "",
                            }
                        )
                    )
            blocks = blocks[: len(obs_valid)]

            # Sync titles
            for j in range(len(obs_valid)):
                blocks[j] = _ensure_obs_block(blocks[j])
                blocks[j]["obs_index"] = j
                blocks[j]["obs_title"] = _s(obs_valid[j].get("title"))

            for obs_i, blk in enumerate(blocks):
                blk = _ensure_obs_block(blk)

                st.markdown("---")
                st.markdown(f"### {_obs_number(comp_i, obs_i)} — {blk['obs_title']}")
                st.markdown("**Major findings (table rows)**")

                if not locked and st.button(
                    "Apply bulk to rows",
                    key=_key("applybulk", comp_i, obs_i),
                    use_container_width=True,
                ):
                    parsed = _parse_bulk_findings(blk["bulk_findings_text"])
                    blk["findings"] = [_ensure_finding_row(x) for x in (parsed or [{}])]
                    st.rerun()

                rows: List[Dict[str, Any]] = blk.get("findings") or [_ensure_finding_row({})]
                new_rows: List[Dict[str, Any]] = []

                for r_idx, rr in enumerate(rows):
                    rr = _ensure_finding_row(rr)

                    st.markdown("<div class='t6-box'>", unsafe_allow_html=True)

                    c1, c2 = st.columns([2.2, 1.0], gap="small")
                    with c1:
                        rr["finding"] = st.text_area(
                            f"Finding #{r_idx + 1}",
                            value=_s(rr.get("finding")),
                            height=70,
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

                    st.markdown("**Photos**")
                    rr = _render_photo_picker_and_preview(
                        urls=urls,
                        labels=labels,
                        rr=rr,
                        fetch_image=fetch_image,
                        locked=locked,
                        scope_key=f"c{comp_i}.o{obs_i}.r{r_idx}",
                    )

                    st.markdown("</div>", unsafe_allow_html=True)
                    new_rows.append(rr)

                # Row controls
                btns = st.columns([1, 1], gap="small")
                with btns[0]:
                    if st.button("Add finding row", key=_key("add_row", comp_i, obs_i), use_container_width=True, disabled=locked):
                        new_rows.append(_ensure_finding_row({}))
                        st.rerun()
                with btns[1]:
                    if st.button("Remove last row", key=_key("rm_row", comp_i, obs_i), use_container_width=True, disabled=locked) and len(new_rows) > 1:
                        new_rows = new_rows[:-1]
                        st.rerun()

                blk["findings"] = new_rows

                # Recommendations
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
                        st.rerun()
                with rbtns[1]:
                    if st.button("Remove last", key=_key("rm_rec", comp_i, obs_i), use_container_width=True, disabled=locked) and len(new_recs) > 1:
                        new_recs = new_recs[:-1]
                        st.rerun()

                blk["recommendations"] = [x for x in new_recs if _s(x)]
                blocks[obs_i] = blk

            comp4["obs_blocks"] = blocks
            find_list[comp_i] = comp4

    st.session_state[SS_FIND] = find_list

    _merge_to_final()
    status_card("Saved", "Findings and recommendations were saved and merged for DOCX generation.", level="success")

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
