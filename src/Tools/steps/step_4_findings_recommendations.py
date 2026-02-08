from __future__ import annotations

import hashlib
import io
import json
from typing import Any, Dict, List, Optional, Tuple, Callable

import streamlit as st
from PIL import Image, ImageEnhance

from src.Tools.utils.types import Tool6Context
from design.components.base_tool_ui import card_open, card_close, status_card


# =============================================================================
# Session keys
# =============================================================================
SS_OBS = "tool6_obs_components"                  # from Step 3
SS_FIND = "tool6_findings_components"            # Step 4 UI storage
SS_FINAL = "tool6_component_observations_final"  # merged output for DOCX
SS_LOCK = "tool6_report_locked"                  # lock flag
SS_PHOTO_BYTES = "photo_bytes"                   # shared cache (used by Tool6 final DOCX)
SS_PHOTO_THUMBS = "photo_thumbs"                 # NEW: thumbs cache (fast UI)
SS_PHOTO_MARKUP_BYTES = "photo_markup_bytes"     # annotated outputs {cache_key: png_bytes}

# =============================================================================
# Google Sheet Audio Source (CSV export)
# =============================================================================
AUDIO_SHEET_ID = "1XxWP-d3lIV4vSxjp-8fo-u9JW0QvsOBjbFkl2mQqApc"
AUDIO_GID = "845246438"  # from your link
AUDIO_TPM_COL = "TPM ID"  # must match the sheet header exactly


# =============================================================================
# Small utils
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _key(*parts: Any) -> str:
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"t6.s4.{h}"


def _inject_gallery_css() -> None:
    """
    Fixed-size tiles, perfectly aligned, responsive.
    """
    st.markdown(
        """
        <style>
          .t6-photo-grid{
            display:grid;
            grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
            gap:12px;
            align-items:start;
          }
          @media (max-width: 520px){
            .t6-photo-grid{ grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
          }
          .t6-photo-card img{
            width:100% !important;
            height:155px !important;           /* ✅ same height */
            object-fit:cover !important;       /* ✅ crop uniformly */
            border-radius:12px !important;
          }
          @media (max-width: 520px){
            .t6-photo-card img{ height:140px !important; }
          }
          .t6-photo-actions{
            display:flex;
            gap:8px;
            margin-top:6px;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _ensure_state() -> None:
    ss = st.session_state
    ss.setdefault(SS_FIND, [])
    ss.setdefault(SS_FINAL, [])
    ss.setdefault(SS_LOCK, False)
    ss.setdefault(SS_PHOTO_BYTES, {})
    ss.setdefault(SS_PHOTO_THUMBS, {})
    ss.setdefault(SS_PHOTO_MARKUP_BYTES, {})

    if not isinstance(ss[SS_FIND], list):
        ss[SS_FIND] = []
    if not isinstance(ss[SS_PHOTO_BYTES], dict):
        ss[SS_PHOTO_BYTES] = {}
    if not isinstance(ss[SS_PHOTO_THUMBS], dict):
        ss[SS_PHOTO_THUMBS] = {}
    if not isinstance(ss[SS_PHOTO_MARKUP_BYTES], dict):
        ss[SS_PHOTO_MARKUP_BYTES] = {}


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
    r.setdefault("Compliance", "")     # ✅ must be exactly "Compliance"
    r.setdefault("photo", "")          # backward single
    r.setdefault("photos", [])         # NEW multi
    r.setdefault("_show_all_photos", True)

    # NEW: editing + markups per photo
    r.setdefault("photo_edits", {})    # {url: {brightness, contrast, color, ...}}
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
                        "_show_all_photos": True,
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
                "_show_all_photos": True,
                "photo_edits": {},
                "photo_markups": {},
            }
        )

    return out


# =============================================================================
# Photo bytes + thumbnail cache (FAST UI)
# =============================================================================
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


def _make_thumb(b: bytes, *, max_w: int = 420, max_h: int = 300, quality: int = 70) -> Optional[bytes]:
    """
    Create a light JPEG/PNG preview for fast rendering.
    """
    try:
        img = Image.open(io.BytesIO(b)).convert("RGB")
        img.thumbnail((max_w, max_h))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except Exception:
        return None


def _cache_thumb(url: str, b: bytes) -> Optional[bytes]:
    thumbs: Dict[str, bytes] = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}
    if url in thumbs and thumbs[url]:
        return thumbs[url]
    tb = _make_thumb(b)
    if tb:
        thumbs[url] = tb
        st.session_state[SS_PHOTO_THUMBS] = thumbs
    return tb


def _prefetch_thumbs(urls: List[str], *, fetch_image: Callable[[str], Tuple[bool, Optional[bytes], str]], limit: int = 60) -> None:
    """
    Prefetch thumbnails for first N URLs (fast) so gallery feels instant.
    """
    urls = [u for u in urls if _s(u)]
    urls = urls[: max(0, int(limit))]

    thumbs: Dict[str, bytes] = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}
    # If already prefetched, skip quickly.
    missing = [u for u in urls if u not in thumbs]
    if not missing:
        return

    # Try to fill quietly (no spinner)
    for u in missing:
        b = _cache_photo_bytes(u, fetch_image=fetch_image)
        if b:
            _cache_thumb(u, b)


# =============================================================================
# Markup cache (depends on BOTH markup payload + edit params)
# =============================================================================
def _markup_cache_key(photo_url: str, markup_payload: Dict[str, Any], edit_params: Dict[str, Any]) -> str:
    raw = photo_url + "::" + json.dumps(markup_payload or {}, ensure_ascii=False, sort_keys=True) + "::" + json.dumps(edit_params or {}, ensure_ascii=False, sort_keys=True)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    return f"{photo_url}::mk::{h}"


def _save_annotated_png_bytes(photo_url: str, markup_payload: Dict[str, Any], edit_params: Dict[str, Any], png_bytes: bytes) -> None:
    cache = st.session_state.get(SS_PHOTO_MARKUP_BYTES, {}) or {}
    cache[_markup_cache_key(photo_url, markup_payload, edit_params)] = png_bytes
    st.session_state[SS_PHOTO_MARKUP_BYTES] = cache


def _get_annotated_png_bytes(photo_url: str, markup_payload: Dict[str, Any], edit_params: Dict[str, Any]) -> Optional[bytes]:
    cache = st.session_state.get(SS_PHOTO_MARKUP_BYTES, {}) or {}
    return cache.get(_markup_cache_key(photo_url, markup_payload, edit_params))


def _apply_edits_to_image_bytes(b: bytes, edits: Dict[str, Any]) -> bytes:
    """
    Non-destructive edits (brightness/contrast/color) using PIL.
    """
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
# Google Sheet Audio fetch by TPM ID
# =============================================================================
@st.cache_data(ttl=120, show_spinner=False)
def _fetch_audio_sheet_rows_csv() -> List[Dict[str, str]]:
    """
    Reads the Google Sheet gid as CSV (must be accessible).
    If sheet is not public / needs auth, you'll need your existing auth approach,
    but this works for public/accessible sheets.
    """
    import pandas as pd

    csv_url = f"https://docs.google.com/spreadsheets/d/{AUDIO_SHEET_ID}/export?format=csv&gid={AUDIO_GID}"
    df = pd.read_csv(csv_url, dtype=str).fillna("")
    return df.to_dict(orient="records")


def _audios_for_tpm_id(tpm_id: str) -> List[str]:
    """
    Finds row where TPM ID matches, then collects any columns that look like audio columns.
    """
    tpm_id = _s(tpm_id)
    if not tpm_id:
        return []

    try:
        rows = _fetch_audio_sheet_rows_csv()
    except Exception:
        return []

    # find exact row (string compare)
    hit: Optional[Dict[str, str]] = None
    for r in rows:
        if _s(r.get(AUDIO_TPM_COL)) == tpm_id:
            hit = r
            break
    if not hit:
        return []

    # collect audio fields (any col name containing 'audio', plus values that look like URLs)
    out: List[str] = []
    for k, v in hit.items():
        kk = _s(k).lower()
        vv = _s(v)
        if not vv:
            continue
        if "audio" in kk or kk.startswith("aud"):
            out.append(vv)

    # de-dup
    dedup: List[str] = []
    seen = set()
    for u in out:
        if u in seen:
            continue
        seen.add(u)
        dedup.append(u)
    return dedup


# =============================================================================
# Merge Step 3 + Step 4 into SS_FINAL (DOCX-ready)
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
                            "Compliance": compliance,  # ✅ EXACT
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
            # audio_url is kept in state but you said NOT needed in report; fine.
            ov_item["audio_url"] = _s(blk.get("audio_url"))
            ov[oi] = ov_item

        comp["observations_valid"] = ov
        final.append(comp)

    st.session_state[SS_FINAL] = final
    return final


# =============================================================================
# Photo Picker + Editor + Annotator UI
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

    photos: List[str] = rr.get("photos") if isinstance(rr.get("photos"), list) else []
    photos = [_s(x) for x in photos if _s(x)]
    rr["photos"] = photos

    rr["_show_all_photos"] = True if not photos else bool(rr.get("_show_all_photos", False))

    # toggle + selected count
    tcol1, tcol2 = st.columns([1, 1], gap="small")
    with tcol1:
        rr["_show_all_photos"] = st.toggle(
            "Show all photos",
            value=rr["_show_all_photos"],
            disabled=locked,
            key=_key("show_all", scope_key),
        )
    with tcol2:
        st.caption(f"Selected: {len(rr['photos'])}" if rr["photos"] else "Selected: 0")

    show_all = rr["_show_all_photos"] or (len(rr["photos"]) == 0)

    # Fast thumb lookup
    thumbs: Dict[str, bytes] = st.session_state.get(SS_PHOTO_THUMBS, {}) or {}

    def _render_tile(purl: str, *, selected: bool) -> None:
        # Use thumb if exists; otherwise try to create one once.
        img_to_show: Optional[bytes] = thumbs.get(purl)

        if img_to_show is None:
            b = _cache_photo_bytes(purl, fetch_image=fetch_image)
            if b:
                img_to_show = _cache_thumb(purl, b)

        st.markdown('<div class="t6-photo-card">', unsafe_allow_html=True)
        if img_to_show:
            st.image(img_to_show, use_container_width=True)
        else:
            st.caption("Image not cached yet.")
        st.markdown("</div>", unsafe_allow_html=True)

        if selected:
            if st.button("Remove", disabled=locked, key=_key("rm_photo", scope_key, purl), use_container_width=True):
                rr["photos"] = [x for x in rr["photos"] if x != purl]
                if not rr["photos"]:
                    rr["_show_all_photos"] = True
        else:
            if st.button("Select", disabled=locked, key=_key("sel_photo", scope_key, purl), use_container_width=True):
                if purl not in rr["photos"]:
                    rr["photos"].append(purl)
                # hide all others immediately
                rr["_show_all_photos"] = False

    # --- Render gallery / selected-only (FAST HIDE)
    if show_all:
        st.markdown("**Photos (choose one or more)**")

        # Prefetch thumbs for first batch to avoid visible loading
        _prefetch_thumbs(urls, fetch_image=fetch_image, limit=60)

        # Render in 3 columns; responsive wrap on mobile
        cols = st.columns(3, gap="small")
        for i, purl in enumerate(urls):
            with cols[i % 3]:
                _render_tile(purl, selected=(purl in rr["photos"]))
    else:
        st.markdown("**Selected photos**")
        cols = st.columns(3, gap="small")
        for i, purl in enumerate(rr["photos"]):
            with cols[i % 3]:
                _render_tile(purl, selected=True)

    rr["photo"] = rr["photos"][0] if rr["photos"] else ""

    # --- Editor + Annotation
    if rr["photos"]:
        st.markdown("**Edit & annotate selected photos (PowerPoint-like)**")

        try:
            from streamlit_drawable_canvas import st_canvas  # type: ignore
            canvas_ok = True
        except Exception:
            canvas_ok = False

        for purl in rr["photos"]:
            with st.expander(f"🖼️ Edit/Annotate: {labels.get(purl, purl)}", expanded=False):
                base_b = _cache_photo_bytes(purl, fetch_image=fetch_image)
                if not base_b:
                    st.error("Image download failed; cannot edit/annotate.")
                    continue

                # EDIT controls
                rr["photo_edits"].setdefault(purl, {"brightness": 1.0, "contrast": 1.0, "color": 1.0})
                edits = rr["photo_edits"][purl]

                e1, e2, e3 = st.columns([1, 1, 1], gap="small")
                with e1:
                    edits["brightness"] = st.slider(
                        "Brightness",
                        0.5, 1.8, float(edits.get("brightness", 1.0)), 0.05,
                        disabled=locked,
                        key=_key("br", scope_key, purl),
                    )
                with e2:
                    edits["contrast"] = st.slider(
                        "Contrast",
                        0.5, 1.8, float(edits.get("contrast", 1.0)), 0.05,
                        disabled=locked,
                        key=_key("ct", scope_key, purl),
                    )
                with e3:
                    edits["color"] = st.slider(
                        "Color",
                        0.0, 2.0, float(edits.get("color", 1.0)), 0.05,
                        disabled=locked,
                        key=_key("cl", scope_key, purl),
                    )

                # Apply edits to background for canvas + preview
                edited_png = _apply_edits_to_image_bytes(base_b, edits)
                st.image(edited_png, use_container_width=True)

                if not canvas_ok:
                    st.info("Annotation tool not available (missing streamlit-drawable-canvas).")
                    rr["photo_edits"][purl] = edits
                    continue

                # ANNOTATION controls (PowerPoint-like)
                rr["photo_markups"].setdefault(purl, {})
                a1, a2, a3, a4 = st.columns([1, 1, 1, 1], gap="small")
                with a1:
                    tool = st.selectbox(
                        "Tool",
                        options=["freedraw", "rect", "circle", "line"],
                        index=0,
                        disabled=locked,
                        key=_key("tool", scope_key, purl),
                    )
                with a2:
                    stroke_w = st.slider(
                        "Stroke",
                        1, 16, 3,
                        disabled=locked,
                        key=_key("sw", scope_key, purl),
                    )
                with a3:
                    stroke_color = st.color_picker(
                        "Stroke color",
                        value="#FF0000",
                        disabled=locked,
                        key=_key("sc", scope_key, purl),
                    )
                with a4:
                    fill_on = st.toggle(
                        "Fill",
                        value=False,
                        disabled=locked,
                        key=_key("fill", scope_key, purl),
                    )

                fill_color = "rgba(255, 0, 0, 0.15)" if fill_on else "rgba(0, 0, 0, 0)"
                # background image for canvas
                bg = Image.open(io.BytesIO(edited_png)).convert("RGBA")

                canvas = st_canvas(
                    fill_color=fill_color,
                    stroke_width=stroke_w,
                    stroke_color=stroke_color,
                    background_image=bg,
                    update_streamlit=True,
                    height=min(560, max(320, int(bg.height * (560 / max(bg.width, 1))))),
                    width=560,
                    drawing_mode=tool,
                    key=_key("canvas", scope_key, purl),
                )

                # Save exact final image bytes (edited + shapes)
                if canvas and canvas.json_data:
                    payload = canvas.json_data
                    rr["photo_markups"][purl] = payload
                    rr["photo_edits"][purl] = edits

                    try:
                        import numpy as np  # type: ignore

                        arr = canvas.image_data
                        if arr is not None and isinstance(arr, np.ndarray):
                            out_img = Image.fromarray(arr.astype("uint8"), mode="RGBA")
                            out_buf = io.BytesIO()
                            out_img.save(out_buf, format="PNG")
                            _save_annotated_png_bytes(purl, payload, edits, out_buf.getvalue())
                            st.success("✅ Saved (will appear exactly in report).")
                    except Exception:
                        st.warning("Saved markup, but could not render PNG bytes here.")

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
        st.subheader("Step 4 — Findings & Recommendations")
        status_card("Step 3 is empty", "Please complete Step 3 (Observations) first.", level="error")
        return False

    locked = _is_locked()

    st.subheader("Step 4 — Findings & Recommendations")

    with st.container(border=True):
        card_open(
            "Findings & Recommendations",
            subtitle="Each observation has a major findings table and recommendations. Titles are locked from Step 3.",
            variant="lg-variant-cyan",
        )

        # Lock controls
        cL, cU = st.columns([1, 1], gap="small")
        with cL:
            st.button(
                "🔒 Lock report before export",
                use_container_width=True,
                disabled=locked,
                on_click=_lock_ui_controls,
                key=_key("lock"),
            )
        with cU:
            st.button(
                "🔓 Unlock",
                use_container_width=True,
                disabled=not locked,
                on_click=_unlock_ui_controls,
                key=_key("unlock"),
            )

        st.divider()

        # Ensure one Step 4 entry per Step 3 component
        find_list: List[Dict[str, Any]] = st.session_state[SS_FIND]
        if len(find_list) < len(obs):
            for i in range(len(find_list), len(obs)):
                find_list.append(_ensure_comp({"comp_index": i, "obs_blocks": []}))
        find_list = find_list[: len(obs)]
        st.session_state[SS_FIND] = find_list

        # Photos list (from ctx)
        urls = getattr(ctx, "all_photo_urls", []) or []
        labels = getattr(ctx, "photo_label_by_url", {}) or {}

        # Prefetch thumbs once at page load (fast gallery)
        if urls:
            _prefetch_thumbs(urls, fetch_image=fetch_image, limit=60)

        # ---------------------------------------------------------------------
        # AUDIO: fetch from Google Sheet by TPM ID
        # ---------------------------------------------------------------------
        # Try to read TPM ID from ctx; if not exist, user can type it.
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
            # show only audio list, choose one, guarantee play
            sel = st.selectbox(
                "Select audio to play",
                options=[""] + audio_urls,
                index=0,
                format_func=lambda u: "Select..." if not u else u,
                key=_key("audio_sel"),
                disabled=locked,
            )
            if sel:
                if fetch_audio is not None:
                    ok, b, _msg, mime = fetch_audio(sel)
                    if ok and b:
                        st.audio(b, format=(mime or "audio/aac").split(";")[0])
                    else:
                        # fallback
                        st.audio(sel)
                else:
                    st.audio(sel)

            st.divider()
        else:
            st.info("No audios found for this TPM ID (or sheet not accessible).")
            st.divider()

        # Tools options
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

                # Ensure one block per observation
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

                # Sync titles from Step 3 (locked)
                for j in range(len(obs_valid)):
                    blocks[j] = _ensure_obs_block(blocks[j])
                    blocks[j]["obs_index"] = j
                    blocks[j]["obs_title"] = _s(obs_valid[j].get("title"))

                # Render each observation block
                for obs_i, blk in enumerate(blocks):
                    blk = _ensure_obs_block(blk)

                    st.markdown("---")
                    st.markdown(f"### {_obs_number(comp_i, obs_i)} — {blk['obs_title']}")

                    st.markdown("**Major findings (table rows)**")

                    # Bulk paste
                    blk["bulk_findings_text"] = st.text_area(
                        "Bulk paste (one row per line) — optional",
                        value=_s(blk.get("bulk_findings_text")),
                        height=90,
                        key=_key("bulk", comp_i, obs_i),
                        disabled=locked,
                        placeholder="Example:\nYes | Pipe leakage observed\nNo | Chlorine testing not conducted",
                    )

                    if not locked and st.button(
                        "Apply bulk to rows",
                        key=_key("applybulk", comp_i, obs_i),
                        use_container_width=True,
                    ):
                        parsed = _parse_bulk_findings(blk["bulk_findings_text"])
                        blk["findings"] = [_ensure_finding_row(x) for x in (parsed or [{}])]

                    # Findings rows
                    rows: List[Dict[str, Any]] = blk.get("findings") or [_ensure_finding_row({})]
                    new_rows: List[Dict[str, Any]] = []

                    for r_idx, rr in enumerate(rows):
                        rr = _ensure_finding_row(rr)

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

                        # Photos section only
                        st.markdown("**Photos**")
                        rr = _render_photo_picker_and_preview(
                            urls=urls,
                            labels=labels,
                            rr=rr,
                            fetch_image=fetch_image,
                            locked=locked,
                            scope_key=f"c{comp_i}.o{obs_i}.r{r_idx}",
                        )

                        new_rows.append(rr)

                    # Row controls
                    btns = st.columns([1, 1], gap="small")
                    with btns[0]:
                        if st.button(
                            "Add finding row",
                            key=_key("add_row", comp_i, obs_i),
                            use_container_width=True,
                            disabled=locked,
                        ):
                            new_rows.append(_ensure_finding_row({}))
                    with btns[1]:
                        if st.button(
                            "Remove last row",
                            key=_key("rm_row", comp_i, obs_i),
                            use_container_width=True,
                            disabled=locked,
                        ) and len(new_rows) > 1:
                            new_rows = new_rows[:-1]

                    blk["findings"] = new_rows

                    # Recommendations
                    st.markdown("**Recommendations (paragraphs)**")
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
                        if st.button(
                            "Add recommendation paragraph",
                            key=_key("add_rec", comp_i, obs_i),
                            use_container_width=True,
                            disabled=locked,
                        ):
                            new_recs.append("")
                    with rbtns[1]:
                        if st.button(
                            "Remove last",
                            key=_key("rm_rec", comp_i, obs_i),
                            use_container_width=True,
                            disabled=locked,
                        ) and len(new_recs) > 1:
                            new_recs = new_recs[:-1]

                    blk["recommendations"] = [x for x in new_recs if _s(x)]
                    blocks[obs_i] = blk

                comp4["obs_blocks"] = blocks
                find_list[comp_i] = comp4

        st.session_state[SS_FIND] = find_list

        # Merge into SS_FINAL (DOCX-ready)
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
