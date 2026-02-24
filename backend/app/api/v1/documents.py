"""Document management API endpoints."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, EditorUser, ReviewerUser, get_db
from app.config.settings import get_settings
from app.core.errors import ConflictError, ErrorCode, NotFoundError, ValidationError
from app.db.models.document import Document, DocumentStatus, Section
from app.schemas.document import (
    DocumentGraphNode,
    DocumentListResponse,
    DocumentOut,
    DocumentUploadResponse,
    SectionOut,
)
from app.services.audit.logger import AuditLogger
from app.services.ingestion.parser import DocumentProcessor

_log = structlog.get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _run_ingestion(document_id: str) -> None:
    """Background task wrapper for document processing."""
    from app.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as db:
        processor = DocumentProcessor(db)
        try:
            await processor.process(document_id)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            _log.error("background_ingestion_failed", document_id=document_id, error=str(exc))


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=201,
    summary="Upload a PDF or DOCX document",
    dependencies=[EditorUser],
)
async def upload_document(
    file: Annotated[UploadFile, File(description="PDF or DOCX file")],
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentUploadResponse:
    """
    Upload a document for processing.

    Validates MIME type and file size, stores file securely, then
    schedules ingestion as a background task.
    """
    settings = get_settings()

    if file.content_type not in settings.allowed_mime_types:
        raise ValidationError(
            f"Unsupported file type: {file.content_type}",
            detail={
                "allowed": settings.allowed_mime_types,
                "received": file.content_type,
            },
        )

    raw = await file.read()
    if len(raw) > settings.max_upload_size_mb * 1024 * 1024:
        raise ValidationError(
            f"File exceeds maximum allowed size of {settings.max_upload_size_mb}MB",
            detail={"size_bytes": len(raw), "limit_bytes": settings.max_upload_size_mb * 1024 * 1024},  # noqa: E501
        )

    file_hash = _sha256(raw)

    # Check for duplicate
    existing = await db.execute(
        select(Document).where(Document.file_hash == file_hash, Document.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        raise ConflictError(
            ErrorCode.DOC_HASH_DUPLICATE,
            "A document with an identical content hash already exists.",
        )

    # Normalise filename to prevent path traversal
    safe_name = f"{uuid.uuid4().hex}{Path(file.filename or 'upload').suffix.lower()}"
    dest = settings.upload_dir / safe_name
    dest.write_bytes(raw)

    doc = Document(
        filename=safe_name,
        original_filename=file.filename or "unknown",
        mime_type=file.content_type or "application/octet-stream",
        file_size_bytes=len(raw),
        file_hash=file_hash,
        status=DocumentStatus.PENDING,
        created_by=current_user.id,
    )
    db.add(doc)
    await db.flush()

    audit = AuditLogger(db)
    await audit.log(
        event_type="document.uploaded",
        actor_id=current_user.id,
        actor_username=current_user.username,
        entity_type="Document",
        entity_id=doc.id,
        payload={"filename": doc.original_filename, "size_bytes": len(raw)},
    )
    await db.commit()

    background_tasks.add_task(_run_ingestion, doc.id)

    _log.info("document_uploaded", document_id=doc.id, filename=safe_name)
    return DocumentUploadResponse(
        id=doc.id,
        original_filename=doc.original_filename,
        status=doc.status,
        file_hash=doc.file_hash,
        created_at=doc.created_at,
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
    dependencies=[ReviewerUser],
)
async def list_documents(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: DocumentStatus | None = Query(default=None),  # noqa: B008
) -> DocumentListResponse:
    """List documents with optional status filter and pagination."""
    query = select(Document).where(Document.deleted_at.is_(None))
    if status:
        query = query.where(Document.status == status)

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    result = await db.execute(
        query.order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = [DocumentOut.model_validate(d) for d in result.scalars().all()]

    return DocumentListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/{document_id}",
    response_model=DocumentOut,
    summary="Get document details",
    dependencies=[ReviewerUser],
)
async def get_document(
    document_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentOut:
    doc = await db.get(Document, document_id)
    if doc is None or doc.is_deleted:
        raise NotFoundError("Document", document_id)
    return DocumentOut.model_validate(doc)


@router.delete(
    "/{document_id}",
    status_code=204,
    summary="Soft-delete a document",
    dependencies=[EditorUser],
)
async def delete_document(
    document_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    doc = await db.get(Document, document_id)
    if doc is None or doc.is_deleted:
        raise NotFoundError("Document", document_id)
    doc.soft_delete()
    audit = AuditLogger(db)
    await audit.log(
        event_type="document.deleted",
        actor_id=current_user.id,
        actor_username=current_user.username,
        entity_type="Document",
        entity_id=doc.id,
    )
    await db.commit()


@router.get(
    "/{document_id}/sections",
    response_model=list[SectionOut],
    summary="List all sections of a document",
    dependencies=[ReviewerUser],
)
async def list_sections(
    document_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SectionOut]:
    doc = await db.get(Document, document_id)
    if doc is None or doc.is_deleted:
        raise NotFoundError("Document", document_id)

    result = await db.execute(
        select(Section)
        .where(Section.document_id == document_id)
        .order_by(Section.sequence_no)
    )
    return [SectionOut.model_validate(s) for s in result.scalars().all()]


@router.get(
    "/{document_id}/graph",
    response_model=list[DocumentGraphNode],
    summary="Get hierarchical content map",
    dependencies=[ReviewerUser],
)
async def get_document_graph(
    document_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DocumentGraphNode]:
    """Return the document as a hierarchical tree of sections."""
    doc = await db.get(Document, document_id)
    if doc is None or doc.is_deleted:
        raise NotFoundError("Document", document_id)

    result = await db.execute(
        select(Section)
        .where(Section.document_id == document_id)
        .order_by(Section.sequence_no)
    )
    sections = list(result.scalars().all())

    # Build tree
    nodes: dict[str, DocumentGraphNode] = {}
    roots: list[DocumentGraphNode] = []

    for s in sections:
        node = DocumentGraphNode(section=SectionOut.model_validate(s))
        nodes[s.id] = node

    for s in sections:
        node = nodes[s.id]
        if s.parent_id and s.parent_id in nodes:
            nodes[s.parent_id].children.append(node)
        else:
            roots.append(node)

    return roots


@router.get(
    "/{document_id}/export",
    summary="Download the exported DOCX for a completed job",
    dependencies=[ReviewerUser],
)
async def export_document(
    document_id: str,
    job_id: str = Query(..., description="Job ID whose assembled output to download"),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> FileResponse:
    """Download the assembled DOCX for an approved job."""
    from app.config.settings import get_settings
    from app.db.models.job import RewriteJob

    job = await db.get(RewriteJob, job_id)
    if job is None or job.document_id != document_id:
        raise NotFoundError("RewriteJob", job_id)

    settings = get_settings()
    # Find most recent export for this job
    candidates = list(settings.export_dir.glob(f"{job_id}_*.docx"))
    if not candidates:
        raise NotFoundError("Export file for job", job_id)

    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return FileResponse(
        path=str(latest),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=f"fillwise_export_{job_id[:8]}.docx",
    )
