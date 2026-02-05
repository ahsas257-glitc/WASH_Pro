# src/auth.py
from __future__ import annotations

import json
import os
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials


# Google API scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _project_root() -> str:
    """Project root = one level above /src."""
    return os.path.dirname(os.path.dirname(__file__))


def get_local_credentials_path() -> str:
    """
    Local development only:
    Put credentials.json in one of:
      - <project_root>/code/credentials.json
      - <project_root>/credentials.json
    """
    root = _project_root()
    candidates = [
        os.path.join(root, "code", "credentials.json"),
        os.path.join(root, "credentials.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    raise FileNotFoundError(
        "credentials.json not found for local dev. "
        "Add it locally (not to GitHub) or use Streamlit Secrets on Cloud."
    )


def _load_service_account_from_streamlit_secrets() -> Optional[dict]:
    """
    Try to load service-account JSON from Streamlit Secrets.

    Supported secret formats:
      1) GOOGLE_CREDENTIALS_JSON = """{...json...}"""
      2) [gcp_service_account] ... key/value pairs (older style)
      3) [google_service_account] ... key/value pairs (alternative style)
    """
    try:
        import streamlit as st  # lazy import
    except Exception:
        return None

    # 1) JSON string (recommended)
    if hasattr(st, "secrets") and "GOOGLE_CREDENTIALS_JSON" in st.secrets:
        raw = st.secrets["GOOGLE_CREDENTIALS_JSON"]
        # st.secrets may return already-str; ensure it's valid JSON
        try:
            return json.loads(raw)
        except Exception as e:
            raise ValueError(
                "Streamlit secret GOOGLE_CREDENTIALS_JSON exists but is not valid JSON. "
                "Make sure you pasted the JSON exactly and preserved \\n in private_key."
            ) from e

    # 2) TOML table (older)
    for table_key in ("gcp_service_account", "google_service_account"):
        if hasattr(st, "secrets") and table_key in st.secrets:
            # st.secrets[table_key] is a mapping-like object
            return dict(st.secrets[table_key])

    return None


def get_gspread_client(credentials_path: Optional[str] = None) -> gspread.Client:
    """
    Return an authorized gspread client.

    - Streamlit Cloud: reads credentials from st.secrets (recommended)
    - Local: reads credentials.json from file path or known locations
    """
    # Prefer Streamlit Secrets if present
    sa_info = _load_service_account_from_streamlit_secrets()
    if sa_info:
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        return gspread.authorize(creds)

    # Fallback: Local dev file
    if credentials_path is None:
        credentials_path = get_local_credentials_path()

    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)
