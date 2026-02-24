"""Audit event schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AuditEventOut(BaseModel):
    id: str
    event_type: str
    actor_id: str | None
    actor_username: str | None
    entity_type: str | None
    entity_id: str | None
    correlation_id: str | None
    event_hash: str
    prev_hash: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditListResponse(BaseModel):
    items: list[AuditEventOut]
    total: int
    page: int
    page_size: int


class ChainVerificationResult(BaseModel):
    is_valid: bool
    total_events: int
    first_broken_at: str | None = Field(
        default=None, description="ID of the first event with a broken hash link"
    )
    message: str
