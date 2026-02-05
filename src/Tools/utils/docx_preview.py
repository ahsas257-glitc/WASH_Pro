from __future__ import annotations

import os
import tempfile
import time
import logging
from typing import Optional


def docx_first_page_to_png(
    docx_bytes: bytes,
    *,
    dpi: int = 170,
    wait_after_save: float = 0.15,
) -> Optional[bytes]:
    """
    Convert first page of DOCX to PNG (Windows-only).

    Pipeline:
      DOCX -> PDF (Microsoft Word COM)
      PDF  -> PNG (PyMuPDF)

    Requirements:
      - Windows
      - Microsoft Word installed
      - pywin32
      - pymupdf

    Returns:
      PNG bytes if successful, otherwise None.

    Safe for Streamlit preview usage.
    """

    # Fast exit
    if not docx_bytes:
        return None

    # Import lazily (important for non-Windows environments)
    try:
        import pythoncom
        import win32com.client  # pywin32
        import fitz  # PyMuPDF
    except Exception:
        return None

    try:
        with tempfile.TemporaryDirectory(prefix="tool6_preview_") as td:
            docx_path = os.path.join(td, "preview.docx")
            pdf_path = os.path.join(td, "preview.pdf")

            # Write DOCX
            with open(docx_path, "wb") as f:
                f.write(docx_bytes)

            # -------------------------
            # DOCX -> PDF via Word COM
            # -------------------------
            pythoncom.CoInitialize()
            word = None
            doc = None

            try:
                word = win32com.client.DispatchEx("Word.Application")
                word.Visible = False
                word.DisplayAlerts = 0  # wdAlertsNone

                doc = word.Documents.Open(
                    docx_path,
                    ReadOnly=True,
                    AddToRecentFiles=False,
                    ConfirmConversions=False,
                    NoEncodingDialog=True,
                )

                # 17 = wdFormatPDF
                doc.SaveAs2(pdf_path, FileFormat=17)

                doc.Close(False)
                doc = None

                # Allow filesystem flush (important on busy systems)
                if wait_after_save > 0:
                    time.sleep(wait_after_save)

            except Exception:
                logging.exception("DOCX → PDF conversion failed (Word COM)")
                return None

            finally:
                try:
                    if doc is not None:
                        doc.Close(False)
                except Exception:
                    pass
                try:
                    if word is not None:
                        word.Quit()
                except Exception:
                    pass
                pythoncom.CoUninitialize()

            # -------------------------
            # PDF -> PNG via PyMuPDF
            # -------------------------
            try:
                pdf = fitz.open(pdf_path)
                if pdf.page_count < 1:
                    pdf.close()
                    return None

                page = pdf.load_page(0)
                pix = page.get_pixmap(dpi=int(dpi))
                png_bytes = pix.tobytes("png")

                pdf.close()
                return png_bytes

            except Exception:
                logging.exception("PDF → PNG rendering failed (PyMuPDF)")
                return None

    except Exception:
        logging.exception("Unexpected error in docx_first_page_to_png")
        return None
