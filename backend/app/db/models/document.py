"""
Document and Section database models.

DocumentStatus tracks the ingestion lifecycle.
SectionType enumerates recognized structural elements.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models.job import RewriteJob, SectionRewrite

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentStatus(StrEnum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    MAPPING = "mapping"
    MAPPED = "mapped"
    FAILED = "failed"


class SectionType(StrEnum):
    PREAMBLE = "preamble"
    HEADING = "heading"
    CLAUSE = "clause"
    DEFINITION = "definition"
    TABLE = "table"
    LIST = "list"
    APPENDIX = "appendix"
    UNKNOWN = "unknown"


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """Uploaded legal document."""

    __tablename__ = "documents"

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus, name="document_status"),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    sections: Mapped[list[Section]] = relationship(
        "Section", back_populates="document", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[RewriteJob]] = relationship(
        "RewriteJob", back_populates="document"
    )

    def __repr__(self) -> str:
        return f"<Document {self.original_filename} [{self.status}]>"


class Section(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A single extracted structural unit of a document.

    Sections form a tree via parent_id. Sequence order is maintained
    by the sequence_no field (1-based, scoped per document).
    """

    __tablename__ = "sections"

    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    section_type: Mapped[SectionType] = mapped_column(
        SAEnum(SectionType, name="section_type"),
        nullable=False,
        default=SectionType.UNKNOWN,
        index=True,
    )
    heading: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    document: Mapped[Document] = relationship("Document", back_populates="sections")
    children: Mapped[list["Section"]] = relationship(
        "Section",
        foreign_keys=[parent_id],
        back_populates="parent",
    )
    parent: Mapped["Section | None"] = relationship(
        "Section",
        foreign_keys=[parent_id],
        back_populates="children",
        remote_side=lambda: [Section.id],
    )
    rewrites: Mapped[list[SectionRewrite]] = relationship(
        "SectionRewrite", back_populates="section"
    )

    def __repr__(self) -> str:
        return f"<Section {self.section_type} seq={self.sequence_no}>"
