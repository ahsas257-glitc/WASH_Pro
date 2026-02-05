# src/Tools/utils/state.py
from __future__ import annotations

import streamlit as st


def init_tool6_state() -> None:
    """
    Lightweight & safe init for Tool 6.
    Keeps keys consistent across steps and avoids heavy defaults.
    """

    # core
    st.session_state.setdefault("tpm_id", None)
    st.session_state.setdefault("general_info_overrides", {})

    # Step 1 (cover)
    st.session_state.setdefault("cover_bytes", None)
    st.session_state.setdefault("Tools_cover_bytes", None)  # optional alias

    # Step 3 caches
    st.session_state.setdefault("photo_bytes", {})   # {url: bytes}
    st.session_state.setdefault("audio_bytes", {})   # {url: bytes}

    # Step 3/4 payloads
    st.session_state.setdefault("component_observations", [])
    st.session_state.setdefault("tool6_component_observations_final", None)

    # Step 8 (severity maps)
    st.session_state.setdefault("tool6_severity_by_no", {})
    st.session_state.setdefault("tool6_severity_by_finding", {})
    st.session_state.setdefault("tool6_add_legend", True)

    # Step 9 (conclusion)
    st.session_state.setdefault("tool6_conclusion_payload", {
        "conclusion_text": "",
        "key_points": [],
        "recommendations_summary": "",
    })

    # Output DOCX
    st.session_state.setdefault("tool6_docx_bytes", None)
