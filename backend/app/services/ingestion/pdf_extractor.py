"""
PDF text extraction service.

Primary extractor: pdfplumber (preserves layout best)
Fallback extractor: pymupdf (faster, different rendering)

Both extractors return a list of (page_number, text) tuples.
"""

from __future__ import annotations

import io
from pathlib import Path

import structlog

_log = structlog.get_logger(__name__)


def _extract_with_pdfplumber(data: bytes) -> list[tuple[int, str]]:
    """Extract pages using pdfplumber."""
    import pdfplumber  # type: ignore[import-untyped]

    pages: list[tuple[int, str]] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            pages.append((i, text.strip()))
    return pages


def _extract_with_pymupdf(data: bytes) -> list[tuple[int, str]]:
    """Fallback extraction via PyMuPDF."""
    import fitz  # type: ignore[import-untyped]  # pymupdf

    pages: list[tuple[int, str]] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text") or ""
            pages.append((i, text.strip()))
    return pages


def extract_pdf(data: bytes) -> list[tuple[int, str]]:
    """
    Extract text from a PDF byte stream.

    Tries pdfplumber first; falls back to PyMuPDF on failure.

    Returns:
        List of (1-based page number, page text) tuples.

    Raises:
        RuntimeError: If both extractors fail.
    """
    try:
        pages = _extract_with_pdfplumber(data)
        _log.debug("pdf_extraction_complete", extractor="pdfplumber", pages=len(pages))
        return pages
    except Exception as primary_err:
        _log.warning("pdfplumber_failed", error=str(primary_err), fallback="pymupdf")

    try:
        pages = _extract_with_pymupdf(data)
        _log.debug("pdf_extraction_complete", extractor="pymupdf", pages=len(pages))
        return pages
    except Exception as fallback_err:
        _log.error("pymupdf_failed", error=str(fallback_err))
        raise RuntimeError(
            f"PDF extraction failed with both extractors: {fallback_err}"
        ) from fallback_err


def extract_pdf_from_path(path: Path) -> list[tuple[int, str]]:
    return extract_pdf(path.read_bytes())
