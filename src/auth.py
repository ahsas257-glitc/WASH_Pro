# src/auth.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

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
        "credentials.json not found for local dev.\n"
        "- Put it in <project_root>/credentials.json or <project_root>/code/credentials.json\n"
        "- Or configure Streamlit Secrets for Cloud."
    )


def _fix_private_key_newlines(sa_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Streamlit secrets sometimes store private_key with real newlines or with '\\n'.
    Google expects actual newlines in the PEM block.
    """
    info = dict(sa_info)
    pk = info.get("private_key")
    if isinstance(pk, str):
        # If it's a JSON string with literal \n, json.loads already converts it to real newlines.
        # But if user pasted it into TOML without escaping, it may contain actual newlines.
        # Also sometimes it contains '\\n' - convert those to '\n'.
        info["private_key"] = pk.replace("\\n", "\n")
    return info


def _load_service_account_from_streamlit_secrets() -> Optional[Dict[str, Any]]:
    """
    Load service account credentials from Streamlit secrets if available.

    Supports:
      1) GOOGLE_CREDENTIALS_JSON = "{...json...}"  (string)
      2) [gcp_service_account] ... key/value pairs (table)
      3) [google_service_account] ... key/value pairs (table)
    """
    try:
        import streamlit as st  # lazy import
    except Exception:
        return None

    if not hasattr(st, "secrets"):
        return None

    # 1) JSON string style (recommended)
    if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
        raw = st.secrets["GOOGLE_CREDENTIALS_JSON"]
        if not isinstance(raw, str):
            # Streamlit may return a Secrets object; enforce str
            raw = str(raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(
                "Streamlit secret GOOGLE_CREDENTIALS_JSON exists but is not valid JSON.\n"
                "Common cause: private_key line breaks were pasted incorrectly.\n"
                "Fix: keep the JSON exactly as downloaded from Google, and ensure private_key uses \\n inside the string."
            ) from e

        if not isinstance(data, dict):
            raise ValueError("GOOGLE_CREDENTIALS_JSON must decode to a JSON object (dict).")

        return _fix_private_key_newlines(data)

    # 2/3) Table style
    for table_key in ("gcp_service_account", "google_service_account"):
        if table_key in st.secrets:
            table = dict(st.secrets[table_key])
            return _fix_private_key_newlines(table)

    return None


def get_gspread_client(credentials_path: Optional[str] = None) -> gspread.Client:
    """
    Return an authorized gspread client.

    Priority:
      1) Streamlit secrets (Cloud)
      2) Local credentials.json file
    """
    # 1) Cloud secrets
    sa_info = _load_service_account_from_streamlit_secrets()
    if sa_info:
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        return gspread.authorize(creds)

    # 2) Local file
    if credentials_path is None:
        credentials_path = get_local_credentials_path()

    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)
