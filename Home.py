# Home.py (اصلاح‌شده) — منطق اصلی حفظ شده، فقط: (1) آپدیت سریع‌تر، (2) Auto-refresh اختیاری، (3) Refresh دستی، (4) Clear cache روی تغییر Tool
from __future__ import annotations

import re
from pathlib import Path

import streamlit as st
from gspread.exceptions import WorksheetNotFound, SpreadsheetNotFound, APIError

from design import apply_glassmorphism  # ✅ design comes from design/ folder
from src.config import GOOGLE_SHEET_ID, TPM_COL, TOOLS
from src.data_processing import fetch_tpm_ids


# -------------------------
# Page config (MUST be first)
# -------------------------
st.set_page_config(page_title="WASH Pro — Home", layout="wide")

# ✅ Apply global design from design/
apply_glassmorphism()
# -------------------------
# Custom style for Refresh button
# -------------------------
st.markdown(
    """
    <style>
    /* فقط دکمه‌های داخل ستون کوچک (Refresh) */
    div[data-testid="column"] button {
        min-height: 42px !important;
        padding: 6px 10px !important;
        font-size: 14px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -------------------------
# OPTIONAL: Auto-refresh (بدون تغییر منطق اصلی)
# اگر پکیج streamlit-autorefresh نصب باشد، هر چند ثانیه یک‌بار rerun می‌کند تا دیتای جدید سریع بیاید.
# نصب (در صورت نیاز): pip install streamlit-autorefresh
# -------------------------
AUTO_REFRESH_MS = 3000  # هر 3 ثانیه
try:
    from streamlit_autorefresh import st_autorefresh

    st_autorefresh(interval=AUTO_REFRESH_MS, key="tpm_poll")
except Exception:
    # اگر نصب نبود، اپ همچنان کار می‌کند؛ فقط realtime اتومات ندارد و با تعامل/Refresh دستی آپدیت می‌شود.
    pass


# -------------------------
# Project root
# -------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
PAGES_DIR = PROJECT_ROOT / "pages"


# -------------------------
# Secrets helper (logic unchanged)
# -------------------------
def _secrets_hint_if_missing_or_blank() -> str | None:
    try:
        if not hasattr(st, "secrets"):
            return "Streamlit secrets not available in this environment."

        if "gcp_service_account" not in st.secrets and "GOOGLE_CREDENTIALS_JSON" not in st.secrets:
            return (
                "No Google credentials found in Streamlit Secrets.\n"
                "Add either:\n"
                "  - [gcp_service_account]\n"
                "  - GOOGLE_CREDENTIALS_JSON"
            )

        if "gcp_service_account" in st.secrets:
            sa = dict(st.secrets["gcp_service_account"])
            if not (sa.get("private_key") or "").strip():
                return "Service account private_key is EMPTY."

        if "GOOGLE_CREDENTIALS_JSON" in st.secrets:
            if not str(st.secrets["GOOGLE_CREDENTIALS_JSON"]).strip():
                return "GOOGLE_CREDENTIALS_JSON secret is EMPTY."
    except Exception:
        return None

    return None


# -------------------------
# Cached loader (منطق حفظ شده؛ فقط TTL کم شده تا سریع آپدیت شود)
# -------------------------
TPM_CACHE_TTL_SEC = 3  # ✅ قبلا 600 بود؛ الان برای آپدیت سریع‌تر

@st.cache_data(ttl=TPM_CACHE_TTL_SEC, show_spinner=False)
def load_tpm_ids_cached(sheet_id: str, tool_name: str, tpm_col: str) -> list[str]:
    return fetch_tpm_ids(sheet_id, tool_name, tpm_col=tpm_col, header_row=1)


def _safe_load_tpm_ids(tool_name: str) -> tuple[list[str], str | None]:
    try:
        ids = load_tpm_ids_cached(GOOGLE_SHEET_ID, tool_name, TPM_COL)
        ids = [str(x).strip() for x in ids if str(x).strip()]
        return ids, None

    except WorksheetNotFound:
        return [], f"Worksheet not found: '{tool_name}'. Please ensure TOOLS match Sheet tab names exactly."

    except SpreadsheetNotFound:
        hint = _secrets_hint_if_missing_or_blank()
        return [], "Spreadsheet not found or not shared." + (f"\n\n{hint}" if hint else "")

    except APIError as e:
        return [], f"Google API Error: {e}"

    except FileNotFoundError:
        return [], "Credentials file not found. Use Streamlit Secrets."

    except Exception as e:
        hint = _secrets_hint_if_missing_or_blank()
        return [], f"Unexpected error: {type(e).__name__}: {e}" + (f"\n\n{hint}" if hint else "")


# -------------------------
# Session defaults (logic unchanged)
# -------------------------
if "selected_tool" not in st.session_state:
    st.session_state["selected_tool"] = "Tool 6" if "Tool 6" in TOOLS else (TOOLS[0] if TOOLS else "")

if "tpm_id" not in st.session_state:
    st.session_state["tpm_id"] = ""


# -------------------------
# Resolver (logic unchanged)
# -------------------------
def _tool_number(tool_label: str) -> int | None:
    m = re.search(r"(\d{1,2})", (tool_label or "").strip())
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _resolve_tool_page_file(selected_tool: str) -> str | None:
    n = _tool_number(selected_tool)
    if n is None:
        return None

    exact = f"Tool_{n}.py"
    if (PAGES_DIR / exact).exists():
        return exact

    for alt in [f"Tool {n}.py", f"Tool{n}.py", f"tool_{n}.py", f"tool{n}.py", f"tool {n}.py"]:
        if (PAGES_DIR / alt).exists():
            return alt

    for p in PAGES_DIR.glob("*.py"):
        if re.search(rf"^tool[\s_]*0*{n}\.py$", p.name, flags=re.IGNORECASE):
            return p.name

    return None


# -------------------------
# UI (Grid-like, no CSS here)
# -------------------------
def _on_tool_change() -> None:
    # منطق شما: reset tpm_id
    st.session_state["tpm_id"] = ""
    # ✅ اضافه شده: برای اینکه بعد از تغییر tool، حتما لیست جدید فوراً از شیت خوانده شود
    load_tpm_ids_cached.clear()


def _refresh_tpm_list() -> None:
    # ✅ دکمه Refresh دستی (بدون دست زدن به منطق اصلی)
    load_tpm_ids_cached.clear()
    st.rerun()


# --- Header (همچنان ساده و بدون CSS) ---
st.markdown("## WASH Pro")
st.markdown("Select a tool and TPM ID to continue.")
st.caption("WASH • UNICEF")

# --- Center the whole content ---
_, mid, _ = st.columns([1, 1.2, 1], vertical_alignment="center")

with mid:
    # ====== GRID (داخل ستون وسط) ======
    # Row 1: Tool
    l1, r1 = st.columns([0.33, 0.67], vertical_alignment="center")
    with l1:
        st.markdown("**Tool**")
    with r1:
        selected_tool = st.selectbox(
            "Tool",
            TOOLS,
            index=TOOLS.index(st.session_state["selected_tool"]) if st.session_state["selected_tool"] in TOOLS else 0,
            key="selected_tool",
            label_visibility="collapsed",
            on_change=_on_tool_change,
        )

    # Row 2: TPM ID + Refresh
    # ✅ ردیف را کمی تغییر دادیم تا کنار TPM ID یک دکمه Refresh داشته باشید (منطق انتخاب همان است)
    l2, r2 = st.columns([0.33, 0.67], vertical_alignment="center")
    with l2:
        st.markdown("**TPM ID**")

    # ✅ ابتدا لیست را لود می‌کنیم
    with st.spinner("Loading TPM list..."):
        tpm_ids, load_error = _safe_load_tpm_ids(selected_tool)

    options = [""] + tpm_ids
    if st.session_state["tpm_id"] not in options:
        st.session_state["tpm_id"] = ""

    with r2:
        sel_col, btn_col = st.columns([0.78, 0.22], vertical_alignment="center")
        with sel_col:
            selected_tpm_id = st.selectbox(
                "TPM ID",
                options=options,
                key="tpm_id",
                label_visibility="collapsed",
            )
        with btn_col:
            st.button("Refresh", on_click=_refresh_tpm_list, use_container_width=True)

    # Tip / Error (داخل همان بخش وسط، زیر گرید)
    if load_error:
        st.error(load_error)
    else:
        st.caption(f"Auto-update: every ~{TPM_CACHE_TTL_SEC}s (cache TTL).")


# ====== BUTTON (خارج از گرید، وسط صفحه، کوچک) ======
_, btn_mid, _ = st.columns([1, 0.35, 1], vertical_alignment="center")

login_disabled = (not st.session_state["tpm_id"]) or bool(load_error)

with btn_mid:
    login_clicked = st.button(
        "Continue",
        type="primary",
        disabled=login_disabled,
        use_container_width=True,
    )


# -------------------------
# Navigation (logic unchanged)
# -------------------------
if login_clicked:
    st.session_state["_tpm_id_locked"] = selected_tpm_id

    page_file = _resolve_tool_page_file(selected_tool)
    if not page_file:
        n = _tool_number(selected_tool)
        st.error(
            f"Cannot resolve target page for: {selected_tool}\n\n"
            f"Expected file: pages/Tool_{n}.py\n"
            f"Pages folder: {PAGES_DIR}"
        )
        st.stop()

    st.switch_page(f"pages/{page_file}")
