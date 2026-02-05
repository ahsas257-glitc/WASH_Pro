import streamlit as st
import traceback

from src.data_processing import fetch_tpm_ids

sheet_id = st.secrets.get("SPREADSHEET_ID", "")
ws_name  = st.secrets.get("TPM_SHEET_NAME", "")

try:
    tpm_ids = fetch_tpm_ids(sheet_id, ws_name, tpm_col="TPM_ID", header_row=1)
    st.success(f"Loaded TPM IDs: {len(tpm_ids)}")
except Exception as e:
    st.error("TPM load failed (raw error):")
    st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)))
    st.stop()
