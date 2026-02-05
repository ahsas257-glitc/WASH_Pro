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
    return os.path.dirname(os.path.dirname(__file__))


def get_local_credentials_path() -> str:
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


def _fix_private_key(sa_info: Dict[str, Any]) -> Dict[str, Any]:
    info = dict(sa_info)
    pk = info.get("private_key")
    if isinstance(pk, str):
        info["private_key"] = pk.replace("\\n", "\n")
    return info


def _validate_sa(sa_info: Dict[str, Any]) -> None:
    required = ["type", "project_id", "private_key", "client_email", "token_uri"]
    missing = [k for k in required if not sa_info.get(k)]
    if missing:
        raise ValueError(
            f"Service account info missing required keys: {missing}.\n"
            "Your Streamlit secrets are incomplete. Make sure you pasted the full service account JSON values."
        )


def _load_service_account_from_streamlit_secrets() -> Optional[Dict[str, Any]]:
    try:
        import streamlit as st
    except Exception:
        return None

    if not hasattr(st, "secrets"):
        return None

    # 1) JSON string style
    if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
        raw = st.secrets["GOOGLE_CREDENTIALS_JSON"]
        raw = raw if isinstance(raw, str) else str(raw)
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("GOOGLE_CREDENTIALS_JSON must decode to a JSON object (dict).")
        data = _fix_private_key(data)
        _validate_sa(data)
        return data

    # 2) Table style
    for table_key in ("gcp_service_account", "google_service_account"):
        if table_key in st.secrets:
            data = dict(st.secrets[table_key])
            data = _fix_private_key(data)
            _validate_sa(data)
            return data

    return None


def get_gspread_client(credentials_path: Optional[str] = None) -> gspread.Client:
    sa_info = _load_service_account_from_streamlit_secrets()
    if sa_info:
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        return gspread.authorize(creds)

    # local fallback (dev)
    if credentials_path is None:
        credentials_path = get_local_credentials_path()

    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)
