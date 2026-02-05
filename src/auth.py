# src/auth.py
from __future__ import annotations

import json
import os
from typing import Optional, Dict, Any

import gspread
from google.oauth2.service_account import Credentials


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
        "Add it locally (do NOT commit to GitHub) or configure Streamlit Secrets on Cloud."
    )


def _load_service_account_from_streamlit_secrets() -> Optional[Dict[str, Any]]:
    """
    Load service-account credentials from Streamlit Secrets (Cloud).

    Supported secret formats:
      1) Key GOOGLE_CREDENTIALS_JSON containing a JSON string (recommended)
      2) Table [gcp_service_account] as key/value pairs (older style)
      3) Table [google_service_account] as key/value pairs (alternative style)
    """
    try:
        import streamlit as st  # lazy import
    except Exception:
        return None

    if not hasattr(st, "secrets"):
        return None

    # 1) Recommended: JSON string stored under GOOGLE_CREDENTIALS_JSON
    if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
        raw = st.secrets["GOOGLE_CREDENTIALS_JSON"]
        try:
            return json.loads(raw)
        except Exception as e:
            raise ValueError(
                "Streamlit secret GOOGLE_CREDENTIALS_JSON exists but is not valid JSON. "
                "Re-check you pasted valid JSON and kept \\n inside private_key."
            ) from e

    # 2/3) TOML table style
    for table_key in ("gcp_service_account", "google_service_account"):
        if table_key in st.secrets:
            try:
                return dict(st.secrets[table_key])
            except Exception as e:
                raise ValueError(f"Streamlit secrets table '{table_key}' is not a valid mapping.") from e

    return None


def get_gspread_client(credentials_path: Optional[str] = None) -> gspread.Client:
    """
    Return an authorized gspread client.

    Priority:
      - Streamlit Cloud: use Streamlit Secrets
      - Local: use credentials.json from disk
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
