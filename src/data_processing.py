# src/data_processing.py
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import gspread
from gspread.exceptions import APIError, WorksheetNotFound, SpreadsheetNotFound

from src.auth import get_gspread_client


# -----------------------------------------
# Internal helpers
# -----------------------------------------
def _is_retryable_api_error(err: Exception) -> bool:
    """
    Decide if we should retry this error.
    Common transient cases:
      - 503 service unavailable
      - 429 too many requests / rate limit
      - 500 internal
      - 502 bad gateway
      - 504 gateway timeout
      - network-like errors sometimes appear as APIError text
    """
    msg = str(err)
    retry_markers = ["[503]", "[429]", "[500]", "[502]", "[504]", "service is currently unavailable"]
    return any(m in msg for m in retry_markers)


def _sleep_with_backoff(attempt: int, base_wait: float) -> None:
    """Exponential backoff: base_wait, 2*base_wait, 4*base_wait, ..."""
    wait = base_wait * (2**attempt)
    time.sleep(wait)


def _col_to_a1(col_idx_1based: int) -> str:
    """1 -> A, 2 -> B, 27 -> AA ..."""
    n = int(col_idx_1based)
    if n <= 0:
        raise ValueError("col index must be >= 1")
    letters = []
    while n:
        n, r = divmod(n - 1, 26)
        letters.append(chr(65 + r))
    return "".join(reversed(letters))


def _open_spreadsheet_with_retry(
    sheet_id: str,
    *,
    retries: int = 4,
    base_wait: float = 1.5,
):
    """
    Open the spreadsheet (by key) with retry/backoff.
    This is more efficient than opening the spreadsheet repeatedly for each tab call.
    """
    gc = get_gspread_client()

    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return gc.open_by_key(sheet_id)

        except SpreadsheetNotFound:
            # Not retryable in practice: usually wrong ID or not shared with service account
            raise

        except APIError as e:
            last_err = e
            if _is_retryable_api_error(e) and attempt < retries - 1:
                _sleep_with_backoff(attempt, base_wait)
                continue
            raise

        except Exception as e:
            last_err = e
            if _is_retryable_api_error(e) and attempt < retries - 1:
                _sleep_with_backoff(attempt, base_wait)
                continue
            raise

    if last_err:
        raise last_err
    raise RuntimeError("Failed to open spreadsheet for unknown reasons.")


def _open_worksheet_with_retry(
    sheet_id: str,
    worksheet_name: str,
    *,
    retries: int = 4,
    base_wait: float = 1.5,
) -> gspread.Worksheet:
    """Internal: open worksheet with retry/backoff."""
    sh = _open_spreadsheet_with_retry(sheet_id, retries=retries, base_wait=base_wait)

    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            return sh.worksheet(worksheet_name)

        except WorksheetNotFound:
            # Not retryable: wrong tab name
            raise

        except APIError as e:
            last_err = e
            if _is_retryable_api_error(e) and attempt < retries - 1:
                _sleep_with_backoff(attempt, base_wait)
                continue
            raise

        except Exception as e:
            last_err = e
            if _is_retryable_api_error(e) and attempt < retries - 1:
                _sleep_with_backoff(attempt, base_wait)
                continue
            raise

    if last_err:
        raise last_err
    raise RuntimeError("Failed to open worksheet for unknown reasons.")


def _fetch_headers(ws: gspread.Worksheet, header_row: int = 1) -> List[str]:
    """Read header row once."""
    return [str(x).strip() for x in ws.row_values(header_row)]


def _find_col_index(headers: List[str], col_name: str) -> Optional[int]:
    """Return 1-based column index of col_name in headers."""
    target = (col_name or "").strip()
    if not target:
        return None
    for i, h in enumerate(headers, start=1):
        if (h or "").strip() == target:
            return i
    return None


def _row_values_by_index(ws: gspread.Worksheet, row_idx: int, max_cols: int) -> List[str]:
    """
    Fetch row values by a bounded A1 range (fast, avoids pulling extra columns).
    """
    end_col_letter = _col_to_a1(max(1, max_cols))
    a1 = f"A{row_idx}:{end_col_letter}{row_idx}"
    data = ws.get(a1, value_render_option="FORMATTED_VALUE")
    if not data:
        return []
    return [str(x) if x is not None else "" for x in (data[0] if data else [])]


def _build_row_dict(headers: List[str], values: List[str]) -> Dict[str, Any]:
    """Convert headers + row values to dict."""
    out: Dict[str, Any] = {}
    for i, h in enumerate(headers):
        key = str(h).strip()
        if not key:
            continue
        out[key] = values[i] if i < len(values) else ""
    return out


def _normalize_ids(values: List[Any], header_row: int = 1) -> List[str]:
    """
    Normalize a list of TPM values:
      - drop header row
      - strip
      - remove blanks
      - unique + sort
    """
    ids: List[str] = []
    for i, v in enumerate(values, start=1):
        if i == header_row:
            continue
        s = str(v).strip()
        if s:
            ids.append(s)
    return sorted(set(ids))


# -----------------------------------------
# Public API (existing) — behavior unchanged
# -----------------------------------------
def open_worksheet(
    sheet_id: str,
    worksheet_name: str,
    retries: int = 4,
    base_wait: float = 1.5,
) -> gspread.Worksheet:
    """
    Open a worksheet(tab) by name from a given Google Sheet ID.
    """
    return _open_worksheet_with_retry(sheet_id, worksheet_name, retries=retries, base_wait=base_wait)


def get_all_records(ws: gspread.Worksheet) -> List[Dict[str, Any]]:
    """Return all worksheet rows as a list of dictionaries (headers used as keys)."""
    return ws.get_all_records()


def list_tpm_ids(records: List[Dict[str, Any]], tpm_col: str = "TPM_ID") -> List[str]:
    """Build a unique, sorted list of TPM IDs from records (in-memory)."""
    ids: List[str] = []
    for r in records:
        v = str(r.get(tpm_col, "")).strip()
        if v:
            ids.append(v)
    return sorted(set(ids))


def find_by_tpm_id(
    records: List[Dict[str, Any]],
    tpm_id: str,
    tpm_col: str = "TPM_ID",
) -> Optional[Dict[str, Any]]:
    """Find the first record matching the provided TPM ID (in-memory)."""
    target = str(tpm_id).strip()
    for r in records:
        if str(r.get(tpm_col, "")).strip() == target:
            return r
    return None


# -----------------------------------------
# Fast row fetch (no get_all_records)
# -----------------------------------------
def get_row_by_tpm_id(
    ws: gspread.Worksheet,
    *,
    tpm_id: str,
    tpm_col: str = "TPM_ID",
    header_row: int = 1,
    retries: int = 3,
    base_wait: float = 1.2,
) -> Optional[Dict[str, Any]]:
    """
    Fetch ONLY the row for a given TPM_ID without pulling the whole sheet.
    """
    target = str(tpm_id).strip()
    if not target:
        return None

    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            headers = _fetch_headers(ws, header_row=header_row)
            if not headers:
                return None

            col_idx = _find_col_index(headers, tpm_col)
            if col_idx is None:
                return None

            tpm_values = ws.col_values(col_idx)
            row_idx = None
            for i, v in enumerate(tpm_values, start=1):
                if i == header_row:
                    continue
                if str(v).strip() == target:
                    row_idx = i
                    break

            if row_idx is None:
                return None

            row_vals = _row_values_by_index(ws, row_idx=row_idx, max_cols=len(headers))
            return _build_row_dict(headers, row_vals)

        except APIError as e:
            last_err = e
            if _is_retryable_api_error(e) and attempt < retries - 1:
                _sleep_with_backoff(attempt, base_wait)
                continue
            raise

        except Exception as e:
            last_err = e
            if _is_retryable_api_error(e) and attempt < retries - 1:
                _sleep_with_backoff(attempt, base_wait)
                continue
            raise

    if last_err:
        raise last_err
    return None


def fetch_row_by_tpm_id(
    sheet_id: str,
    worksheet_name: str,
    *,
    tpm_id: str,
    tpm_col: str = "TPM_ID",
    header_row: int = 1,
    ws_retries: int = 4,
    ws_base_wait: float = 1.5,
    row_retries: int = 3,
    row_base_wait: float = 1.2,
) -> Optional[Dict[str, Any]]:
    """Convenience: open worksheet + fetch a single TPM row (fast)."""
    ws = _open_worksheet_with_retry(sheet_id, worksheet_name, retries=ws_retries, base_wait=ws_base_wait)
    return get_row_by_tpm_id(
        ws,
        tpm_id=tpm_id,
        tpm_col=tpm_col,
        header_row=header_row,
        retries=row_retries,
        base_wait=row_base_wait,
    )


# -----------------------------------------
# Fast TPM list for dropdown (only TPM column) — behavior unchanged
# -----------------------------------------
def list_tpm_ids_fast(
    ws: gspread.Worksheet,
    *,
    tpm_col: str = "TPM_ID",
    header_row: int = 1,
    retries: int = 3,
    base_wait: float = 1.2,
) -> List[str]:
    """
    Build a unique, sorted list of TPM IDs WITHOUT pulling the entire sheet.
    Reads only:
      - header row
      - TPM column values
    """
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            headers = _fetch_headers(ws, header_row=header_row)
            if not headers:
                return []

            col_idx = _find_col_index(headers, tpm_col)
            if col_idx is None:
                return []

            values = ws.col_values(col_idx)
            return _normalize_ids(values, header_row=header_row)

        except APIError as e:
            last_err = e
            if _is_retryable_api_error(e) and attempt < retries - 1:
                _sleep_with_backoff(attempt, base_wait)
                continue
            raise

        except Exception as e:
            last_err = e
            if _is_retryable_api_error(e) and attempt < retries - 1:
                _sleep_with_backoff(attempt, base_wait)
                continue
            raise

    if last_err:
        raise last_err
    return []


def fetch_tpm_ids(
    sheet_id: str,
    worksheet_name: str,
    *,
    tpm_col: str = "TPM_ID",
    header_row: int = 1,
    ws_retries: int = 4,
    ws_base_wait: float = 1.5,
    list_retries: int = 3,
    list_base_wait: float = 1.2,
) -> List[str]:
    """
    Convenience: open worksheet + fetch TPM id list fast.
    Use for dropdowns.

    ✅ IMPORTANT: This returns TPM IDs ONLY from the selected worksheet_name (tool tab).
    """
    ws = _open_worksheet_with_retry(sheet_id, worksheet_name, retries=ws_retries, base_wait=ws_base_wait)
    return list_tpm_ids_fast(
        ws,
        tpm_col=tpm_col,
        header_row=header_row,
        retries=list_retries,
        base_wait=list_base_wait,
    )


# -----------------------------------------
# Streamlit-friendly caching hooks — behavior unchanged
# -----------------------------------------
def get_worksheet_cached(sheet_id: str, worksheet_name: str):
    """OPTIONAL helper: for Streamlit use with st.cache_resource."""
    return open_worksheet(sheet_id, worksheet_name)


def get_row_cached(
    sheet_id: str,
    worksheet_name: str,
    *,
    tpm_id: str,
    tpm_col: str = "TPM_ID",
    header_row: int = 1,
):
    """OPTIONAL helper: for Streamlit use with st.cache_data (per worksheet + TPM)."""
    return fetch_row_by_tpm_id(
        sheet_id,
        worksheet_name,
        tpm_id=tpm_id,
        tpm_col=tpm_col,
        header_row=header_row,
    )


def get_tpm_ids_cached(
    sheet_id: str,
    worksheet_name: str,
    *,
    tpm_col: str = "TPM_ID",
    header_row: int = 1,
):
    """OPTIONAL helper: for Streamlit use with st.cache_data (per worksheet)."""
    return fetch_tpm_ids(
        sheet_id,
        worksheet_name,
        tpm_col=tpm_col,
        header_row=header_row,
    )
