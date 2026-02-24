"""
DOCX text extraction service.

Extracts paragraphs with their style names, table cell text, and
basic structural metadata from DOCX files.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import structlog

_log = structlog.get_logger(__name__)


@dataclass
class ExtractedParagraph:
    """A single paragraph with its inline style information."""

    text: str
    style_name: str
    is_bold: bool
    is_italic: bool
    paragraph_index: int


@dataclass
class ExtractedTable:
    """Flat text representation of a DOCX table."""

    rows: list[list[str]]  # [row][col] = cell text
    paragraph_index: int


@dataclass
class DocxContent:
    """Structured content extracted from a DOCX file."""

    paragraphs: list[ExtractedParagraph]
    tables: list[ExtractedTable]

    @property
    def all_text(self) -> str:
        """Convenience: join all paragraph text."""
        return "\n".join(p.text for p in self.paragraphs if p.text.strip())


def extract_docx(data: bytes) -> DocxContent:
    """
    Extract structured content from a DOCX byte stream.

    Returns:
        DocxContent with paragraphs and tables in document order.

    Raises:
        RuntimeError: If the file cannot be parsed as a valid DOCX.
    """
    from docx import Document  # type: ignore[import-untyped]

    try:
        doc = Document(io.BytesIO(data))
    except Exception as err:
        raise RuntimeError(f"DOCX parsing failed: {err}") from err

    paragraphs: list[ExtractedParagraph] = []
    tables: list[ExtractedTable] = []
    paragraph_index = 0

    # Iterate all block-level elements in order to preserve sequence
    body = doc.element.body
    for element in body:
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

        if tag == "p":
            # Paragraph element
            from docx.text.paragraph import Paragraph  # type: ignore[import-untyped]

            para = Paragraph(element, doc)
            text = para.text.strip()
            if not text:
                paragraph_index += 1
                continue

            style_name = para.style.name if para.style else "Normal"
            is_bold = any(run.bold for run in para.runs if run.text.strip())
            is_italic = any(run.italic for run in para.runs if run.text.strip())

            paragraphs.append(
                ExtractedParagraph(
                    text=text,
                    style_name=style_name,
                    is_bold=is_bold,
                    is_italic=is_italic,
                    paragraph_index=paragraph_index,
                )
            )
            paragraph_index += 1

        elif tag == "tbl":
            from docx.table import Table  # type: ignore[import-untyped]

            table = Table(element, doc)
            rows: list[list[str]] = []
            for row in table.rows:
                rows.append([cell.text.strip() for cell in row.cells])

            tables.append(ExtractedTable(rows=rows, paragraph_index=paragraph_index))
            paragraph_index += 1

    _log.debug(
        "docx_extraction_complete",
        paragraphs=len(paragraphs),
        tables=len(tables),
    )
    return DocxContent(paragraphs=paragraphs, tables=tables)


def extract_docx_from_path(path: Path) -> DocxContent:
    return extract_docx(Path(path).read_bytes())
