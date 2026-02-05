# src/auth.py
from __future__ import annotations

import os
from typing import Optional, Dict, Any

import gspread
from google.oauth2.service_account import Credentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(__file__))


def get_local_credentials_path() -> str:
    """
    Local development:
      Put your credentials.json in one of:
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
        "credentials.json not found. Add it locally (DO NOT push to GitHub) "
        "or configure Streamlit Cloud secrets under [gcp_service_account]."
    )


def _load_service_account_from_streamlit_secrets() -> Optional[Dict[str, Any]]:
    """
    Streamlit Cloud:
      Read service account from Secrets table:
        [gcp_service_account]
        ...
    This format supports real newlines in private_key and is the safest.
    """
    try:
        import streamlit as st  # lazy import
    except Exception:
        return None

    if not hasattr(st, "secrets"):
        return None

    if "gcp_service_account" in st.secrets:
        return dict(st.secrets["gcp_service_account"])

    # (Optional) allow alternative name if you ever use it
    if "google_service_account" in st.secrets:
        return dict(st.secrets["google_service_account"])

    return None


def get_gspread_client(credentials_path: Optional[str] = None) -> gspread.Client:
    """
    Returns an authorized gspread client.

    Priority:
      1) Streamlit Cloud Secrets: [gcp_service_account]
      2) Local credentials.json file (for local dev only)
    """
    sa_info = _load_service_account_from_streamlit_secrets()
    if sa_info:
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        return gspread.authorize(creds)

    # Local fallback
    if credentials_path is None:
        credentials_path = get_local_credentials_path()

    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)
