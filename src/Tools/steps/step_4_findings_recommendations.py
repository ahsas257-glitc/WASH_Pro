from __future__ import annotations

import hashlib
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


# =============================================================================
# Small utils
# =============================================================================
def _s(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _key(*parts: Any) -> str:
    """
    Short, stable Streamlit keys (avoid DuplicateWidgetID).
    """
    raw = ".".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"t6.s4.{h}"


def _ensure_state() -> None:
    ss = st.session_state
    ss.setdefault(SS_FIND, [])
    ss.setdefault(SS_FINAL, [])
    ss.setdefault(SS_LOCK, False)
    ss.setdefault(SS_PHOTO_BYTES, {})

    if not isinstance(ss[SS_FIND], list):
        ss[SS_FIND] = []
    if not isinstance(ss[SS_PHOTO_BYTES], dict):
        ss[SS_PHOTO_BYTES] = {}


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
    r.setdefault("Compliance", "")
    r.setdefault("photo", "")  # URL only (bytes go to SS_PHOTO_BYTES)
    return r


def _is_locked() -> bool:
    return bool(st.session_state.get(SS_LOCK, False))


def _lock_ui_controls() -> None:
    st.session_state[SS_LOCK] = True


def _unlock_ui_controls() -> None:
    st.session_state[SS_LOCK] = False


def _obs_number(comp_index: int, obs_index: int) -> str:
    # UI numbering only
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
                    }
                )
                continue

        out.append({"Compliance": "", "finding": line, "photo": ""})

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
            title, text, audio_url, photos,
            major_table: [{finding, Tools, photo, photo_bytes}],
            recommendations: [str...]
          }
        ]
      }
    ]
    """
    obs = st.session_state.get(SS_OBS, []) or []
    find = st.session_state.get(SS_FIND, []) or []
    photo_cache: Dict[str, bytes] = st.session_state.get(SS_PHOTO_BYTES, {}) or {}

    final: List[Dict[str, Any]] = []

    for comp_index, comp3 in enumerate(obs):
        comp = {
            "comp_id": _s(comp3.get("comp_id")),
            "title": _s(comp3.get("title")),
            # IMPORTANT: keep the list object, but we will safely mutate items
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
                tools_val = _s(rr.get("Compliance"))
                photo = _s(rr.get("photo"))
                photo_bytes = photo_cache.get(photo) if photo else None

                if finding or tools_val or photo:
                    major_table.append(
                        {
                            "finding": finding,
                            "Compliance": tools_val,
                            "photo": photo,
                            "photo_bytes": photo_bytes,
                        }
                    )

            recs = [x for x in (blk.get("recommendations") or []) if _s(x)]

            ov_item = ov[oi]
            ov_item["title"] = _s(blk.get("obs_title")) or _s(ov_item.get("title"))
            ov_item["major_table"] = major_table
            ov_item["recommendations"] = recs
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

                    # Audio (optional)
                    if audio_urls:
                        a1, a2 = st.columns([2, 1], gap="small")
                        with a1:
                            cur = _s(blk.get("audio_url"))
                            opts = [""] + audio_urls
                            idx = opts.index(cur) if cur in opts else 0
                            blk["audio_url"] = st.selectbox(
                                "Audio (optional)",
                                options=opts,
                                index=idx,
                                format_func=lambda u: "None" if not u else audio_label.get(u, u),
                                key=_key("audio", comp_i, obs_i),
                                disabled=locked,
                            )
                        with a2:
                            st.caption("Play")
                            if blk["audio_url"]:
                                if fetch_audio is not None:
                                    ok, b, _msg, mime = fetch_audio(blk["audio_url"])
                                    if ok and b:
                                        st.audio(b, format=(mime or "audio/aac").split(";")[0])
                                    else:
                                        st.audio(blk["audio_url"])
                                else:
                                    st.audio(blk["audio_url"])

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

                        c1, c2, c3 = st.columns([2.2, 1.0, 1.6], gap="small")
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
                        with c3:
                            prev_photo = _s(rr.get("photo"))
                            opts = [""] + urls
                            idx = opts.index(prev_photo) if prev_photo in opts else 0
                            rr["photo"] = st.selectbox(
                                "Photo",
                                options=opts,
                                index=idx,
                                format_func=lambda u: "—" if u == "" else labels.get(u, u),
                                key=_key("photo", comp_i, obs_i, r_idx),
                                disabled=locked,
                            )

                        # Preview + cache bytes (only if photo selected)
                        photo_url = _s(rr.get("photo"))
                        if photo_url:
                            bts = _cache_photo_bytes(photo_url, fetch_image=fetch_image)
                            if bts:
                                st.image(bts, width=260)
                            else:
                                st.caption("Image download failed. Please verify access/URL.")

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
