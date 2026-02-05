# src/auth.py
import json
import os
import tempfile
from typing import Optional

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
    Put your credentials.json in: <project_root>/code/credentials.json or <project_root>/credentials.json
    Update this path if your file location is different.
    """
    root = _project_root()
    candidates = [
        os.path.join(root, "code", "credentials.json"),
        os.path.join(root, "credentials.json"),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("credentials.json not found. Add it locally or use Streamlit Cloud secrets.")


def get_gspread_client(credentials_path: Optional[str] = None):
    """
    Returns an authorized gspread client.

    Streamlit Cloud option:
      - Add your service account JSON into st.secrets["gcp_service_account"].
    Local option:
      - Provide credentials_path or place credentials.json in known locations.
    """
    # Lazy import to avoid requiring .streamlit in non-UI modules
    try:
        import streamlit as st
        secrets_available = hasattr(st, "secrets") and ("gcp_service_account" in st.secrets)
    except Exception:
        secrets_available = False

    if secrets_available:
        # Streamlit Cloud: read JSON from secrets and write to temp file
        import streamlit as st
        sa_info = dict(st.secrets["gcp_service_account"])
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        return gspread.authorize(creds)

    # Local: read from file path
    if credentials_path is None:
        credentials_path = get_local_credentials_path()

    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)
