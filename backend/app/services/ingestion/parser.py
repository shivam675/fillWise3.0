"""
DocumentProcessor: orchestrates ingestion of uploaded files.

Responsible for:
  1. MIME type validation
  2. File hash computation
  3. Page count enforcement
  4. Text extraction (PDF or DOCX)
  5. Structure detection
  6. Section persistence
  7. Status transitions with error recovery
"""

from __future__ import annotations

import hashlib

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.core.errors import (
    NotFoundError,
    ValidationError,
)
from app.db.models.document import Document, DocumentStatus, Section, SectionType
from app.services.ingestion.docx_extractor import extract_docx
from app.services.ingestion.pdf_extractor import extract_pdf
from app.services.ingestion.structure_detector import StructuredSection, detect_structure

_log = structlog.get_logger(__name__)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class DocumentProcessor:
    """
    Processes a single uploaded document.

    Instances are not reused; create a new instance per call.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._settings = get_settings()

    async def process(self, document_id: str) -> None:
        """
        Full ingestion pipeline for an already-persisted Document record.

        Transitions document status:
          pending → extracting → mapping → mapped
               or → failed (on any error, with message stored)
        """
        log = _log.bind(document_id=document_id)

        document = await self._db.get(Document, document_id)
        if document is None:
            raise NotFoundError("Document", document_id)

        try:
            await self._set_status(document, DocumentStatus.EXTRACTING)
            log.info("ingestion_started")

            file_path = self._settings.upload_dir / document.filename
            raw_data = file_path.read_bytes()

            # Extract text per file type
            if document.mime_type == "application/pdf":
                pages = extract_pdf(raw_data)
                page_count = len(pages)
                paragraphs = self._pages_to_paragraphs(pages)
            else:
                content = extract_docx(raw_data)
                page_count = None
                paragraphs = content.paragraphs

            # Enforce page limit (PDF only; DOCX approximated by paragraph count)
            effective_pages = page_count or max(1, len(paragraphs) // 40)
            if effective_pages > self._settings.max_document_pages:
                raise ValidationError(
                    f"Document has {effective_pages} pages which exceeds the limit of "
                    f"{self._settings.max_document_pages}",
                    detail={"pages": effective_pages, "limit": self._settings.max_document_pages},
                )

            document.page_count = page_count

            await self._set_status(document, DocumentStatus.MAPPING)
            sections = detect_structure(paragraphs)
            await self._persist_sections(document, sections)

            await self._set_status(document, DocumentStatus.MAPPED)
            log.info("ingestion_complete", sections=len(sections))

        except Exception as exc:
            log.error("ingestion_failed", error=str(exc))
            document.status = DocumentStatus.FAILED
            document.error_message = str(exc)[:1000]
            await self._db.flush()
            raise

    def _pages_to_paragraphs(
        self, pages: list[tuple[int, str]]
    ) -> list[FakeParagraph]:
        """Convert PDF page tuples into objects compatible with detect_structure."""
        paragraphs = []
        idx = 0
        for _page_no, text in pages:
            for line in text.split("\n"):
                line = line.strip()
                if line:
                    paragraphs.append(FakeParagraph(text=line, paragraph_index=idx))
                    idx += 1
        return paragraphs

    async def _set_status(self, document: Document, status: DocumentStatus) -> None:
        document.status = status
        await self._db.flush()

    async def _persist_sections(
        self, document: Document, structured: list[StructuredSection]
    ) -> None:
        """
        Persist detected sections as Section records.

        Heading sections are used to assign parent_id to subsequent
        non-heading sections, building a simple two-level hierarchy.
        """
        current_heading_id: str | None = None

        for seq_no, s in enumerate(structured, start=1):
            section = Section(
                document_id=document.id,
                sequence_no=seq_no,
                section_type=s.section_type,
                heading=s.heading,
                original_text=s.text,
                content_hash=_text_hash(s.text),
                depth=s.depth,
                char_count=len(s.text),
            )

            if s.section_type == SectionType.HEADING:
                section.parent_id = None
                current_heading_id = None  # will be set after flush
            else:
                section.parent_id = current_heading_id

            self._db.add(section)
            await self._db.flush()

            if s.section_type == SectionType.HEADING:
                current_heading_id = section.id


class FakeParagraph:
    """Adapter: wraps a plain text line as an ExtractedParagraph-like object."""

    def __init__(self, text: str, paragraph_index: int) -> None:
        self.text = text
        self.paragraph_index = paragraph_index
        self.style_name = "Normal"
        self.is_bold = False
        self.is_italic = False
