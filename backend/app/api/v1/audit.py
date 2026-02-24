"""Audit log API endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, get_db
from app.db.models.audit import AuditEvent
from app.schemas.audit import AuditEventOut, AuditListResponse, ChainVerificationResult
from app.services.audit.logger import AuditLogger

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get(
    "",
    response_model=AuditListResponse,
    summary="List audit events",
    dependencies=[AdminUser],
)
async def list_audit_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    event_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
) -> AuditListResponse:
    """Return paginated audit events with optional filters."""
    query = select(AuditEvent)
    if event_type:
        query = query.where(AuditEvent.event_type == event_type)
    if entity_id:
        query = query.where(AuditEvent.entity_id == entity_id)
    if actor_id:
        query = query.where(AuditEvent.actor_id == actor_id)

    count = await db.execute(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.order_by(AuditEvent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return AuditListResponse(
        items=[AuditEventOut.model_validate(e) for e in result.scalars().all()],
        total=count.scalar_one(),
        page=page,
        page_size=page_size,
    )


@router.get(
    "/verify",
    response_model=ChainVerificationResult,
    summary="Verify audit hash chain integrity",
    dependencies=[AdminUser],
)
async def verify_chain(db: Annotated[AsyncSession, Depends(get_db)]) -> ChainVerificationResult:
    """
    Cryptographically verify the audit event hash chain.

    Returns a verification result indicating whether the chain is intact
    and, if not, the ID of the first broken link.
    """
    count_result = await db.execute(select(func.count()).select_from(AuditEvent))
    total = count_result.scalar_one()

    is_valid, broken_at = await AuditLogger.verify_chain(db)

    return ChainVerificationResult(
        is_valid=is_valid,
        total_events=total,
        first_broken_at=broken_at,
        message="Chain is intact." if is_valid else f"Chain broken at event {broken_at}.",
    )
