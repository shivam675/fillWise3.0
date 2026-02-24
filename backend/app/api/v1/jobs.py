"""Rewrite job API endpoints."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, EditorUser, ReviewerUser, get_db
from app.config.settings import get_settings
from app.core.errors import (
    ConflictError,
    ErrorCode,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.db.models.document import Document, DocumentStatus, Section
from app.db.models.job import JobStatus, RewriteJob, RewriteStatus, SectionRewrite
from app.db.models.ruleset import Ruleset
from app.schemas.job import (
    CreateJobRequest,
    JobListResponse,
    RewriteJobOut,
    SectionRewriteOut,
)
from app.services.assembly.docx_builder import AssemblyEngine
from app.services.audit.logger import AuditLogger
from app.services.llm.client import OllamaClient

_log = structlog.get_logger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


async def _schedule_rewrites(job: RewriteJob, sections: list[Section], db: AsyncSession) -> None:
    """Create pending SectionRewrite records for each section."""
    settings = get_settings()
    for section in sections:
        rewrite = SectionRewrite(
            job_id=job.id,
            section_id=section.id,
            status=RewriteStatus.PENDING,
            prompt_hash="",
            prompt_text="",
            model_name=settings.ollama_model,
        )
        db.add(rewrite)

    job.total_sections = len(sections)
    await db.flush()


@router.post(
    "",
    response_model=RewriteJobOut,
    status_code=201,
    summary="Create and start a rewrite job",
    dependencies=[EditorUser],
)
async def create_job(
    body: CreateJobRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RewriteJobOut:
    """
    Create a rewrite job for a document using an active ruleset.

    The job is created and section rewrites are scheduled immediately.
    Actual LLM execution is driven by the WebSocket connection at
    /ws/jobs/{id}, which streams tokens to the client in real time.
    """
    doc = await db.get(Document, body.document_id)
    if doc is None or doc.is_deleted:
        raise NotFoundError("Document", body.document_id)
    if doc.status != DocumentStatus.MAPPED:
        raise ValidationError(
            f"Document must be in MAPPED status to start a job. Current: {doc.status}",
            detail={"status": doc.status},
        )

    ruleset = await db.get(Ruleset, body.ruleset_id)
    if ruleset is None or ruleset.is_deleted:
        raise NotFoundError("Ruleset", body.ruleset_id)
    if not ruleset.is_active:
        raise ValidationError(
            "Ruleset is not active. Activate it before use.",
            detail={"ruleset_id": body.ruleset_id},
        )

    # Fail fast if LLM backend is offline/unhealthy
    if not await OllamaClient().health_check():
        raise ServiceUnavailableError(
            ErrorCode.JOB_OLLAMA_UNAVAILABLE,
            "Ollama is unavailable. Start Ollama and ensure the configured model is pulled.",
        )

    # Prevent duplicate running jobs on same document
    existing = await db.execute(
        select(RewriteJob).where(
            RewriteJob.document_id == body.document_id,
            RewriteJob.status == JobStatus.RUNNING,
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(
            ErrorCode.JOB_ALREADY_RUNNING,
            "A job is already running for this document.",
        )

    # Fetch target sections
    section_query = select(Section).where(Section.document_id == body.document_id)
    if body.section_ids:
        section_query = section_query.where(Section.id.in_(body.section_ids))
    section_query = section_query.order_by(Section.sequence_no)
    section_result = await db.execute(section_query)
    sections = list(section_result.scalars().all())

    if not sections:
        raise ValidationError("No sections found to rewrite.", detail={})

    job = RewriteJob(
        document_id=body.document_id,
        ruleset_id=body.ruleset_id,
        status=JobStatus.PENDING,
        created_by=current_user.id,
        total_sections=0,
        completed_sections=0,
    )
    db.add(job)
    await db.flush()

    await _schedule_rewrites(job, sections, db)

    audit = AuditLogger(db)
    await audit.log(
        event_type="job.created",
        actor_id=current_user.id,
        actor_username=current_user.username,
        entity_type="RewriteJob",
        entity_id=job.id,
        payload={
            "document_id": body.document_id,
            "ruleset_id": body.ruleset_id,
            "sections": len(sections),
        },
    )
    await db.commit()

    # Job execution starts when the frontend connects via WebSocket
    # (see ws.py) – this enables real-time token streaming.
    return RewriteJobOut.model_validate(job)


@router.get(
    "",
    response_model=JobListResponse,
    summary="List rewrite jobs",
    dependencies=[ReviewerUser],
)
async def list_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    document_id: str | None = Query(default=None),
    status: JobStatus | None = Query(default=None),  # noqa: B008
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> JobListResponse:
    query = select(RewriteJob)
    if document_id:
        query = query.where(RewriteJob.document_id == document_id)
    if status:
        query = query.where(RewriteJob.status == status)

    count = await db.execute(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(RewriteJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return JobListResponse(
        items=[RewriteJobOut.model_validate(j) for j in result.scalars().all()],
        total=count.scalar_one(),
    )


@router.get(
    "/{job_id}",
    response_model=RewriteJobOut,
    summary="Get job details",
    dependencies=[ReviewerUser],
)
async def get_job(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RewriteJobOut:
    job = await db.get(RewriteJob, job_id)
    if job is None:
        raise NotFoundError("RewriteJob", job_id)
    return RewriteJobOut.model_validate(job)


@router.get(
    "/{job_id}/rewrites",
    response_model=list[SectionRewriteOut],
    summary="List section rewrites for a job",
    dependencies=[ReviewerUser],
)
async def list_rewrites(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SectionRewriteOut]:
    job = await db.get(RewriteJob, job_id)
    if job is None:
        raise NotFoundError("RewriteJob", job_id)

    result = await db.execute(
        select(SectionRewrite)
        .where(SectionRewrite.job_id == job_id)
        .order_by(SectionRewrite.created_at)
    )
    rewrites = list(result.scalars().all())
    out = []
    for r in rewrites:
        await db.refresh(r, ["risk_findings"])
        out.append(SectionRewriteOut.model_validate(r))
    return out


@router.post(
    "/{job_id}/assemble",
    status_code=202,
    summary="Assemble approved sections into DOCX",
    dependencies=[EditorUser],
)
async def assemble_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """
    Trigger DOCX assembly for all approved sections in a job.

    Returns immediately; assembly runs in background.
    Download the result via /documents/{id}/export?job_id=...
    """
    job = await db.get(RewriteJob, job_id)
    if job is None:
        raise NotFoundError("RewriteJob", job_id)

    if job.status != JobStatus.COMPLETED:
        raise ConflictError(
            ErrorCode.ASSEMBLY_FAILED,
            f"Job is in status '{job.status}'; assembly requires COMPLETED.",
        )

    # ── Pre-flight: ensure every rewrite has an approved review ──────
    from app.db.models.review import Review, ReviewStatus

    rewrite_result = await db.execute(
        select(SectionRewrite).where(SectionRewrite.job_id == job_id)
    )
    rewrites = list(rewrite_result.scalars().all())

    rewrite_ids = [r.id for r in rewrites]
    reviews_by_rewrite: dict[str, Review] = {}
    if rewrite_ids:
        review_result = await db.execute(
            select(Review).where(Review.rewrite_id.in_(rewrite_ids))
        )
        reviews_by_rewrite = {r.rewrite_id: r for r in review_result.scalars().all()}

    unreviewed = [r for r in rewrites if r.id not in reviews_by_rewrite]
    if unreviewed:
        raise ValidationError(
            f"{len(unreviewed)} page(s) have not been reviewed yet. "
            "Review all pages before assembling.",
            detail={"unreviewed_rewrite_ids": [r.id for r in unreviewed]},
        )

    unapproved = [
        r for r in rewrites
        if r.id in reviews_by_rewrite
        and reviews_by_rewrite[r.id].status not in (ReviewStatus.APPROVED, ReviewStatus.EDITED)
    ]
    if unapproved:
        raise ValidationError(
            f"{len(unapproved)} page(s) have not been approved. "
            "Approve or edit all pages before assembling.",
            detail={"unapproved_rewrite_ids": [r.id for r in unapproved]},
        )

    async def _assemble(jid: str, username: str) -> None:
        from app.db.session import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            engine = AssemblyEngine(session)
            try:
                path = await engine.assemble(jid, username)
                _log.info("assembly_done", path=str(path))
                await session.commit()
            except Exception as exc:
                await session.rollback()
                _log.error("assembly_failed", job_id=jid, error=str(exc))

    background_tasks.add_task(_assemble, job_id, current_user.username)
    return {"message": "Assembly started. Download when ready via /documents/{id}/export"}


@router.post(
    "/{job_id}/restart",
    response_model=RewriteJobOut,
    summary="Restart a stuck or failed job",
    dependencies=[EditorUser],
)
async def restart_job(
    job_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RewriteJobOut:
    """
    Restart a job that is stuck, failed, or needs to be rerun.

    Resets pending/failed sections to PENDING. Execution resumes when the
    frontend reconnects via WebSocket.
    """
    job = await db.get(RewriteJob, job_id)
    if job is None:
        raise NotFoundError("RewriteJob", job_id)

    if job.status == JobStatus.RUNNING:
        raise ConflictError(
            ErrorCode.JOB_ALREADY_RUNNING,
            "Job is currently running. Wait for completion or cancel first.",
        )

    # Reset failed/stuck sections to pending
    await db.execute(
        update(SectionRewrite)
        .where(
            SectionRewrite.job_id == job_id,
            SectionRewrite.status.in_([RewriteStatus.FAILED, RewriteStatus.RUNNING]),
        )
        .values(status=RewriteStatus.PENDING)
    )

    job.status = JobStatus.PENDING
    job.error_message = None
    # Reset completed count for sections being retried
    job.completed_sections = 0
    await db.commit()

    audit = AuditLogger(db)
    await audit.log(
        event_type="job.restarted",
        actor_id=current_user.id,
        actor_username=current_user.username,
        entity_type="RewriteJob",
        entity_id=job_id,
        payload={"restarted_by": current_user.username},
    )

    return RewriteJobOut.model_validate(job)


@router.get(
    "/{job_id}/debug",
    summary="Debug job status and section details",
    dependencies=[EditorUser],
)
async def debug_job(
    job_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, object]:
    """
    Get detailed debugging information about a job and its sections.
    
    Useful for diagnosing stuck or failed jobs.
    """
    job = await db.get(RewriteJob, job_id)
    if job is None:
        raise NotFoundError("RewriteJob", job_id)

    # Get all rewrites with their statuses
    result = await db.execute(
        select(SectionRewrite)
        .where(SectionRewrite.job_id == job_id)
        .order_by(SectionRewrite.created_at)
    )
    rewrites = list(result.scalars().all())

    status_counts = {}
    for rewrite in rewrites:
        status_counts[rewrite.status.value] = status_counts.get(rewrite.status.value, 0) + 1

    return {
        "job_id": job_id,
        "job_status": job.status.value,
        "total_sections": job.total_sections,
        "completed_sections": job.completed_sections,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "status_breakdown": status_counts,
        "rewrites": [
            {
                "id": r.id,
                "section_id": r.section_id,
                "status": r.status.value,
                "error_message": r.error_message,
                "attempts": r.attempt_number,
                "tokens": r.tokens_completion,
                "duration_ms": r.duration_ms,
            }
            for r in rewrites
        ],
    }
