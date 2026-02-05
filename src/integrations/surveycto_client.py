from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import requests
import streamlit as st
from streamlit_js_eval import streamlit_js_eval

# =============================================================================
# SurveyCTO server configuration
# =============================================================================
SURVEYCTO_SERVER = "act4performance"

# IMPORTANT:
# BASE_URL must be ONLY the server root (NO /index.html here)
BASE_URL = f"https://{SURVEYCTO_SERVER}.surveycto.com"

# User-facing login page (for display only)
LOGIN_PAGE_URL = f"{BASE_URL}/index.html"

# =============================================================================
# sessionStorage keys (per-tab)
# =============================================================================
_SS_USER = "scto_username"
_SS_PASS = "scto_password"
_SS_OK = "scto_logged_in"
_SS_TEST_URL = "scto_test_attachment_url"

# =============================================================================
# sessionStorage helpers
# =============================================================================
def _ss_get(key: str) -> str:
    v = streamlit_js_eval(
        js_expressions=f"sessionStorage.getItem('{key}')",
        key=f"ss_get_{key}",
        want_output=True,
    )
    if v in (None, "null"):
        return ""
    return str(v)


def _ss_set(key: str, value: str) -> None:
    value = (value or "").replace("\\", "\\\\").replace("'", "\\'")
    streamlit_js_eval(
        js_expressions=f"sessionStorage.setItem('{key}', '{value}')",
        key=f"ss_set_{key}",
        want_output=False,
    )


def _ss_remove(key: str) -> None:
    streamlit_js_eval(
        js_expressions=f"sessionStorage.removeItem('{key}')",
        key=f"ss_rm_{key}",
        want_output=False,
    )

# =============================================================================
# State load/save
# =============================================================================
def load_auth_state() -> None:
    if "scto_username" not in st.session_state:
        st.session_state["scto_username"] = _ss_get(_SS_USER)

    if "scto_password" not in st.session_state:
        st.session_state["scto_password"] = _ss_get(_SS_PASS)

    if "scto_logged_in" not in st.session_state:
        st.session_state["scto_logged_in"] = (_ss_get(_SS_OK) == "1")

    if "scto_test_attachment_url" not in st.session_state:
        st.session_state["scto_test_attachment_url"] = _ss_get(_SS_TEST_URL)


def persist_auth_state(
    username: str,
    password: str,
    logged_in: bool,
    test_attachment_url: str = "",
) -> None:
    st.session_state["scto_username"] = username or ""
    st.session_state["scto_password"] = password or ""
    st.session_state["scto_logged_in"] = bool(logged_in)
    st.session_state["scto_test_attachment_url"] = test_attachment_url or ""

    _ss_set(_SS_USER, username or "")
    _ss_set(_SS_PASS, password or "")
    _ss_set(_SS_OK, "1" if logged_in else "0")
    _ss_set(_SS_TEST_URL, test_attachment_url or "")


def clear_auth_state() -> None:
    st.session_state["scto_username"] = ""
    st.session_state["scto_password"] = ""
    st.session_state["scto_logged_in"] = False
    st.session_state["scto_test_attachment_url"] = ""

    _ss_remove(_SS_USER)
    _ss_remove(_SS_PASS)
    _ss_remove(_SS_OK)
    _ss_remove(_SS_TEST_URL)


def is_logged_in() -> bool:
    return (
        bool(st.session_state.get("scto_logged_in"))
        and bool(st.session_state.get("scto_username"))
        and bool(st.session_state.get("scto_password"))
    )

# =============================================================================
# URL helpers
# =============================================================================
def scto_url_to_path(full_url: str) -> str:
    """
    Convert full attachment URL to relative path.
    """
    p = urlparse(full_url)
    path = (p.path or "").lstrip("/")
    if p.query:
        path = f"{path}?{p.query}"
    return path


def is_scto_server_url(url: str) -> bool:
    try:
        host = (urlparse(url).netloc or "").lower()
        return host == f"{SURVEYCTO_SERVER}.surveycto.com"
    except Exception:
        return False

# =============================================================================
# Attachment validation (ONLY validation we use)
# =============================================================================
def _ping_attachment(
    username: str,
    password: str,
    attachment_url: str,
) -> Tuple[bool, int, str]:
    """
    Validate credentials by requesting a submission-attachment URL.
    """
    r = requests.get(
        attachment_url,
        auth=(username, password),
        timeout=20,
        allow_redirects=True,
    )

    ctype = (r.headers.get("Content-Type") or "").lower()
    if r.status_code == 200 and ctype.startswith(("image/", "audio/")):
        return True, 200, "OK"

    body = (r.text or "").strip()
    if len(body) > 200:
        body = body[:200] + "..."
    return False, r.status_code, body or f"HTTP {r.status_code}"

# =============================================================================
# Login UI
# =============================================================================
def surveycto_login_ui(
    *,
    in_sidebar: bool = True,
    attachment_test_url: str = "",
) -> bool:
    """
    Attachment-first login UI (without showing any test URL input).

    Behavior:
    - If attachment_test_url is provided by the caller (e.g., Tool 6),
      login is validated by opening that attachment link.
    - If no test URL is provided, credentials are stored and attachment access
      will be checked when loading files.
    """
    load_auth_state()
    ui = st.sidebar if in_sidebar else st

    ui.markdown("## SurveyCTO Login")
    ui.caption(f"{SURVEYCTO_SERVER}.surveycto.com")

    username = ui.text_input(
        "Email / Username",
        value=st.session_state.get("scto_username", ""),
        key="ui_scto_username",
    )
    password = ui.text_input(
        "Password",
        value=st.session_state.get("scto_password", ""),
        type="password",
        key="ui_scto_password",
    )

    c1, c2 = ui.columns(2)
    login_clicked = c1.button("Login", use_container_width=True)
    logout_clicked = c2.button("Logout", use_container_width=True)

    if logout_clicked:
        clear_auth_state()
        ui.success("Logged out ✅")
        return False

    if is_logged_in():
        ui.success("Logged in ✅")
        return True

    if login_clicked:
        if not username or not password:
            ui.error("Please enter both username and password.")
            persist_auth_state(username, password, False, test_attachment_url="")
            return False

        # If caller provides an attachment URL, validate silently
        if attachment_test_url:
            ok, status, msg = _ping_attachment(username, password, attachment_test_url)
            if ok:
                persist_auth_state(username, password, True, test_attachment_url=attachment_test_url)
                ui.success("Login successful ✅")
                return True

            persist_auth_state(username, password, False, test_attachment_url=attachment_test_url)
            ui.error(f"Login failed ❌ (HTTP {status})")
            if msg:
                ui.caption(msg)
            return False

        # No test URL → just store credentials
        persist_auth_state(username, password, True, test_attachment_url="")
        ui.success("Logged in ✅")
        ui.caption("Attachment access will be verified when files are loaded.")
        return True

    return False

# =============================================================================
# Safe request wrapper
# =============================================================================
def surveycto_request(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    data: Any = None,
    json: Any = None,
    timeout: int = 30,
) -> requests.Response:
    """
    Use this for ALL SurveyCTO HTTP calls (attachments).
    """
    load_auth_state()
    if not is_logged_in():
        raise RuntimeError("Not logged in to SurveyCTO.")

    username = st.session_state["scto_username"]
    password = st.session_state["scto_password"]

    url = BASE_URL.rstrip("/") + "/" + path.lstrip("/")

    r = requests.request(
        method.upper(),
        url,
        auth=(username, password),
        params=params,
        data=data,
        json=json,
        timeout=timeout,
        allow_redirects=True,
    )

    # Only invalidate login on REAL auth failure
    if r.status_code == 401:
        persist_auth_state(
            username,
            password,
            False,
            st.session_state.get("scto_test_attachment_url", ""),
        )

    return r

# =============================================================================
# Fetch attachment bytes
# =============================================================================
def fetch_attachment_bytes(
    full_url: str,
    *,
    timeout: int = 30,
) -> Tuple[bool, Optional[bytes], str, str]:
    """
    Fetch image/audio attachment using logged-in user's credentials.
    """
    load_auth_state()

    if not is_logged_in():
        return False, None, "Not logged in.", ""

    if not full_url or not full_url.startswith("http"):
        return False, None, "Invalid URL.", ""

    if not is_scto_server_url(full_url):
        return False, None, "URL is not for this SurveyCTO server.", ""

    try:
        path = scto_url_to_path(full_url)
        r = surveycto_request("GET", path, timeout=timeout)

        ctype = (r.headers.get("Content-Type") or "").split(";")[0].lower()

        if r.status_code == 200 and r.content:
            return True, r.content, "OK", ctype

        return False, None, f"HTTP {r.status_code}", ctype

    except Exception as e:
        return False, None, str(e), ""
