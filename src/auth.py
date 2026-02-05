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


# -----------------------------
# Local helper (only for dev)
# -----------------------------
def _project_root() -> str:
    return os.path.dirname(os.path.dirname(__file__))


def get_local_credentials_path() -> str:
    """
    Local development only.
    Put credentials.json in:
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


# -----------------------------
# Secrets parsing helpers
# -----------------------------
def _fix_private_key(sa_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure private_key contains REAL newlines.
    Accepts both '\\n' and real '\n'.
    """
    info = dict(sa_info)
    pk = info.get("private_key")
    if isinstance(pk, str):
        info["private_key"] = pk.replace("\\n", "\n")
    return info


def _validate_service_account_dict(sa_info: Dict[str, Any]) -> None:
    """
    Validate required fields exist. Raise ValueError with clear message if not.
    """
    required = ["type", "project_id", "private_key", "client_email", "token_uri"]
    missing = [k for k in required if not sa_info.get(k)]
    if missing:
        raise ValueError(
            f"Service account info missing required keys: {missing}. "
            "Check your Streamlit Secrets. "
            "Recommended secret format: [gcp_service_account] table or GOOGLE_CREDENTIALS_JSON string."
        )


def _load_from_env() -> Optional[Dict[str, Any]]:
    """
    Optional: allow credentials via env var (useful in some deployments).
    Supported env vars:
      - GOOGLE_CREDENTIALS_JSON
      - GCP_SERVICE_ACCOUNT_JSON
    """
    raw = os.getenv("GOOGLE_CREDENTIALS_JSON") or os.getenv("GCP_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Env GOOGLE_CREDENTIALS_JSON must be a JSON object (dict).")
        data = _fix_private_key(data)
        _validate_service_account_dict(data)
        return data
    except Exception as e:
        raise ValueError(
            "Environment credentials JSON exists but is invalid. "
            "Ensure it is valid JSON and private_key contains \\n escapes."
        ) from e


def _load_from_streamlit_secrets() -> Optional[Dict[str, Any]]:
    """
    Load service account credentials from Streamlit secrets.
    Supports:
      1) GOOGLE_CREDENTIALS_JSON = """{...json...}"""
      2) [gcp_service_account] ... key/value pairs
      3) [google_service_account] ... key/value pairs
    """
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
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(
                "Streamlit secret GOOGLE_CREDENTIALS_JSON is not valid JSON.\n"
                "Most common cause: private_key was pasted with real newlines.\n"
                "Fix: paste the original JSON file exactly, where private_key contains \\n."
            ) from e

        if not isinstance(data, dict):
            raise ValueError("GOOGLE_CREDENTIALS_JSON must decode to a JSON object (dict).")

        data = _fix_private_key(data)
        _validate_service_account_dict(data)
        return data

    # 2/3) Table style
    for table_key in ("gcp_service_account", "google_service_account"):
        if table_key in st.secrets:
            data = dict(st.secrets[table_key])
            data = _fix_private_key(data)
            _validate_service_account_dict(data)
            return data

    return None


def _load_service_account() -> Optional[Dict[str, Any]]:
    """
    Load credentials from:
      1) Streamlit Secrets
      2) Environment variables (optional)
    """
    sa = _load_from_streamlit_secrets()
    if sa:
        return sa

    sa = _load_from_env()
    if sa:
        return sa

    return None


# -----------------------------
# Public API
# -----------------------------
def get_gspread_client(credentials_path: Optional[str] = None) -> gspread.Client:
    """
    Return an authorized gspread client.

    Priority:
      1) Streamlit Secrets / Env (Cloud)
      2) Local credentials.json (dev only)

    IMPORTANT:
      - If you are using Streamlit Cloud, you should configure secrets.
      - If secrets exist but are invalid, we raise a clear error (do not fall back to local).
    """
    sa_info = _load_service_account()
    if sa_info:
        creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
        return gspread.authorize(creds)

    # No secrets/env found -> local fallback (dev)
    if credentials_path is None:
        credentials_path = get_local_credentials_path()

    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    return gspread.authorize(creds)
