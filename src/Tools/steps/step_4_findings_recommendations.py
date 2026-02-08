from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple, Callable

import streamlit as st

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

# NEW: annotated photo outputs
SS_PHOTO_MARKUP_BYTES = "photo_markup_bytes"     # {cache_key: png_bytes}


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
    st.markdown(
        """
        <style>
          .t6-photo-grid{
            display:grid;
            grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
            gap:12px;
            align-items:start;
          }
          @media (min-width: 1400px){
            .t6-photo-grid{ grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); }
          }
          @media (max-width: 520px){
            .t6-photo-grid{ grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); }
          }
          .t6-photo-card img{
            width:100% !important;
            height:160px !important;
            object-fit:cover !important;
            border-radius:12px !important;
          }
          @media (max-width: 520px){
            .t6-photo-card img{ height:140px !important; }
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
    ss.setdefault(SS_PHOTO_MARKUP_BYTES, {})

    if not isinstance(ss[SS_FIND], list):
        ss[SS_FIND] = []
    if not isinstance(ss[SS_PHOTO_BYTES], dict):
        ss[SS_PHOTO_BYTES] = {}
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
    # IMPORTANT: the column must be named Compliance
    r.setdefault("Compliance", "")
    # Backward compatible single field
    r.setdefault("photo", "")
    # NEW: multi-photo selection
    r.setdefault("photos", [])  # List[str]
    # UI helper: hide/show all after selection
    r.setdefault("_show_all_photos", True)
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
                    }
                )
                continue

        out.append({"Compliance": "", "finding": line, "photo": "", "photos": [], "_show_all_photos": True})

    return out


# =============================================================================
# Photo cache: store bytes globally (fast + reused by DOCX)
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


def _markup_cache_key(photo_url: str, markup_payload: Dict[str, Any]) -> str:
    raw = photo_url + "::" + json.dumps(markup_payload or {}, ensure_ascii=False, sort_keys=True)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    return f"{photo_url}::mk::{h}"


def _save_annotated_png_bytes(photo_url: str, markup_payload: Dict[str, Any], png_bytes: bytes) -> None:
    cache = st.session_state.get(SS_PHOTO_MARKUP_BYTES, {}) or {}
    cache[_markup_cache_key(photo_url, markup_payload)] = png_bytes
    st.session_state[SS_PHOTO_MARKUP_BYTES] = cache


def _get_annotated_png_bytes(photo_url: str, markup_payload: Dict[str, Any]) -> Optional[bytes]:
    cache = st.session_state.get(SS_PHOTO_MARKUP_BYTES, {}) or {}
    return cache.get(_markup_cache_key(photo_url, markup_payload))


# =============================================================================
# Merge Step 3 + Step 4 into SS_FINAL (DOCX-ready)
# =============================================================================
def _merge_to_final() -> List[Dict[str, Any]]:
    """
    SS_FINAL output:
    [
      {
        comp_id, title,
        observations_valid: [
          {
            title, text, audio_url,
            major_table: [
              {
                finding, Compliance,
                photos: [url...],
                photo_bytes_list: [bytes|None...],
                annotated_photo_bytes_list: [bytes|None...],
              }
            ],
            recommendations: [str...]
          }
        ]
      }
    ]
    """
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

                # Multi photos
                photos = rr.get("photos") if isinstance(rr.get("photos"), list) else []
                photos = [ _s(x) for x in photos if _s(x) ]

                # Backward compatible single photo if user used old UI
                single_photo = _s(rr.get("photo"))
                if single_photo and single_photo not in photos:
                    photos = photos + [single_photo]

                # bytes list
                photo_bytes_list: List[Optional[bytes]] = []
                annotated_bytes_list: List[Optional[bytes]] = []

                # Optional: per-photo markup payload saved in row
                markups = rr.get("photo_markups") if isinstance(rr.get("photo_markups"), dict) else {}

                for purl in photos:
                    photo_bytes_list.append(photo_cache.get(purl))

                    payload = markups.get(purl) if isinstance(markups.get(purl), dict) else {}
                    if payload:
                        key = _markup_cache_key(purl, payload)
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
# Photo Picker + Annotator UI
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
    """
    Behavior:
    - If no photo selected yet => show ALL photos (grid) with Select buttons
    - If 1+ selected => hide others and show only selected (with Remove)
    - User can toggle "Show all photos" to re-open the full list
    - Each selected photo has optional annotation (pen/shapes)
    """
    rr = _ensure_finding_row(rr)

    # Ensure list
    photos: List[str] = rr.get("photos") if isinstance(rr.get("photos"), list) else []
    photos = [_s(x) for x in photos if _s(x)]
    rr["photos"] = photos

    show_all_default = True if not photos else bool(rr.get("_show_all_photos", False))
    rr["_show_all_photos"] = show_all_default

    # Toggle
    tcol1, tcol2 = st.columns([1, 1], gap="small")
    with tcol1:
        rr["_show_all_photos"] = st.toggle(
            "Show all photos",
            value=rr["_show_all_photos"],
            disabled=locked,
            key=_key("show_all", scope_key),
        )
    with tcol2:
        if photos:
            st.caption(f"Selected: {len(photos)}")

    show_all = rr["_show_all_photos"] or (len(photos) == 0)

    # --- helper: render a single tile
    def render_tile(purl: str, *, selected: bool) -> None:
        bts = _cache_photo_bytes(purl, fetch_image=fetch_image)
        st.markdown('<div class="t6-photo-card">', unsafe_allow_html=True)
        if bts:
            st.image(bts, use_container_width=True)
        else:
            st.caption("Image download failed.")
            st.write(labels.get(purl, purl))
        st.markdown("</div>", unsafe_allow_html=True)

        if selected:
            if st.button("Remove", disabled=locked, key=_key("rm_photo", scope_key, purl), use_container_width=True):
                rr["photos"] = [x for x in rr["photos"] if x != purl]
                # if empty after remove -> show all again
                if not rr["photos"]:
                    rr["_show_all_photos"] = True
        else:
            if st.button("Select", disabled=locked, key=_key("sel_photo", scope_key, purl), use_container_width=True):
                if purl not in rr["photos"]:
                    rr["photos"].append(purl)
                # after select -> hide others
                rr["_show_all_photos"] = False

    # --- grid render
    if show_all:
        st.markdown("**Photos (choose one or more)**")
        st.markdown('<div class="t6-photo-grid">', unsafe_allow_html=True)
        # We render using columns trick; Streamlit can't place arbitrary HTML children reliably,
        # so we simulate grid with columns per row.
        # But CSS still helps with image sizing consistency.
        # We'll do a simple responsive pattern: 4 cols desktop, 3 medium, 2 small (manual).
        # Streamlit doesn't give viewport, so we use 3 columns default and it wraps on mobile.
        cols = st.columns(3, gap="small")
        for i, purl in enumerate(urls):
            with cols[i % 3]:
                render_tile(purl, selected=(purl in rr["photos"]))
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown("**Selected photos**")
        cols = st.columns(3, gap="small")
        for i, purl in enumerate(rr["photos"]):
            with cols[i % 3]:
                render_tile(purl, selected=True)

    # Backward compatible single photo field (keep first)
    rr["photo"] = rr["photos"][0] if rr["photos"] else ""

    # --- Annotation section (optional)
    if rr["photos"]:
        st.markdown("**Annotate selected photos (optional)**")
        try:
            from streamlit_drawable_canvas import st_canvas  # type: ignore
            canvas_ok = True
        except Exception:
            canvas_ok = False

        rr.setdefault("photo_markups", {})  # {url: payload}

        for purl in rr["photos"]:
            with st.expander(f"✍️ Annotate: {labels.get(purl, purl)}", expanded=False):
                bts = _cache_photo_bytes(purl, fetch_image=fetch_image)
                if not bts:
                    st.caption("Cannot annotate because the image could not be downloaded.")
                    continue

                if not canvas_ok:
                    st.info("Annotation tool is not available on this deployment (missing streamlit-drawable-canvas).")
                    st.image(bts, use_container_width=True)
                    continue

                # Controls
                a1, a2, a3 = st.columns([1, 1, 1], gap="small")
                with a1:
                    tool = st.selectbox(
                        "Tool",
                        options=["freedraw", "rect", "circle", "line"],
                        index=0,
                        disabled=locked,
                        key=_key("ann_tool", scope_key, purl),
                    )
                with a2:
                    stroke_width = st.slider(
                        "Stroke",
                        min_value=1,
                        max_value=12,
                        value=3,
                        disabled=locked,
                        key=_key("ann_stroke", scope_key, purl),
                    )
                with a3:
                    fill = st.toggle(
                        "Fill shapes",
                        value=False,
                        disabled=locked,
                        key=_key("ann_fill", scope_key, purl),
                    )

                # Canvas
                # NOTE: We do not force a color (your requirement was mainly size/UX).
                # st_canvas needs background_image as PIL Image. We'll convert bytes to PIL safely.
                from PIL import Image
                import io

                bg = Image.open(io.BytesIO(bts)).convert("RGBA")

                canvas = st_canvas(
                    fill_color="rgba(255, 0, 0, 0.15)" if fill else "rgba(0, 0, 0, 0)",
                    stroke_width=stroke_width,
                    stroke_color="#FF0000",
                    background_image=bg,
                    update_streamlit=True,
                    height=min(520, max(280, int(bg.height * (520 / max(bg.width, 1))))),
                    width=520,
                    drawing_mode=tool,
                    key=_key("ann_canvas", scope_key, purl),
                )

                # Save markup payload + rendered image
                if canvas and canvas.json_data:
                    payload = canvas.json_data
                    rr["photo_markups"][purl] = payload

                    # Render final annotated PNG bytes
                    try:
                        # canvas.image_data is RGBA numpy array
                        import numpy as np  # type: ignore
                        img_arr = canvas.image_data
                        if img_arr is not None and isinstance(img_arr, np.ndarray):
                            out_img = Image.fromarray(img_arr.astype("uint8"), mode="RGBA")
                            out_buf = io.BytesIO()
                            out_img.save(out_buf, format="PNG")
                            _save_annotated_png_bytes(purl, payload, out_buf.getvalue())
                            st.caption("✅ Annotation saved (will be used in report).")
                    except Exception:
                        st.caption("Saved markup, but could not render annotated PNG on this environment.")

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

        # Audio list (optional)
        audios = getattr(ctx, "audios", []) or []
        audio_urls: List[str] = []
        audio_label: Dict[str, str] = {}
        for i, a in enumerate(audios, start=1):
            if isinstance(a, dict):
                u = _s(a.get("url"))
                f = _s(a.get("field")) or "Audio"
                if u:
                    audio_urls.append(u)
                    audio_label[u] = f"{i:02d}. {f}"

        tools_opts = ["", "Yes", "No", "N/A"]

        # --- GLOBAL AUDIO PLAYER SECTION (Audio only)
        if audio_urls:
            st.markdown("### 🎧 Audios")
            st.caption("Play audios here, then write findings while listening.")
            for u in audio_urls:
                with st.container(border=True):
                    st.markdown(f"**{audio_label.get(u, u)}**")
                    if fetch_audio is not None:
                        ok, b, _msg, mime = fetch_audio(u)
                        if ok and b:
                            st.audio(b, format=(mime or "audio/aac").split(";")[0])
                        else:
                            st.audio(u)
                    else:
                        st.audio(u)

            st.divider()

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

                    # Per-observation audio link (Audio only)
                    if audio_urls:
                        cur = _s(blk.get("audio_url"))
                        opts = [""] + audio_urls
                        idx = opts.index(cur) if cur in opts else 0
                        blk["audio_url"] = st.selectbox(
                            "Attach audio to this observation (optional)",
                            options=opts,
                            index=idx,
                            format_func=lambda u: "None" if not u else audio_label.get(u, u),
                            key=_key("audio_attach", comp_i, obs_i),
                            disabled=locked,
                        )

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

                        # --- Photos only section for this finding row
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

        # Merge into SS_FINAL
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
