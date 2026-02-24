"""Document and Section Pydantic schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models.document import DocumentStatus, SectionType


class DocumentUploadResponse(BaseModel):
    id: str
    original_filename: str
    status: DocumentStatus
    file_hash: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentOut(BaseModel):
    id: str
    original_filename: str
    mime_type: str
    file_size_bytes: int
    file_hash: str
    page_count: int | None
    status: DocumentStatus
    error_message: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class SectionOut(BaseModel):
    id: str
    document_id: str
    parent_id: str | None
    sequence_no: int
    depth: int
    section_type: SectionType
    heading: str | None
    original_text: str
    content_hash: str
    page_start: int | None
    page_end: int | None
    char_count: int

    model_config = {"from_attributes": True}


class DocumentGraphNode(BaseModel):
    """Nested tree representation of the document content map."""

    section: SectionOut
    children: list[DocumentGraphNode] = Field(default_factory=list)
