"""Job and SectionRewrite schemas."""

from __future__ import annotations

import json as _json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.db.models.job import JobStatus, RewriteStatus, RiskSeverity


class CreateJobRequest(BaseModel):
    name: str | None = Field(default=None, description="Optional name for the job")
    document_id: str = Field(..., description="Document to rewrite")
    ruleset_id: str = Field(..., description="Ruleset to apply")
    section_ids: list[str] | None = Field(
        default=None,
        description="Optional subset of section IDs to rewrite. Null = all sections.",
    )


class RiskFindingOut(BaseModel):
    id: str
    severity: RiskSeverity
    category: str
    description: str
    score: float
    detail_json: dict[str, Any] | None = None
    created_at: datetime | None = None

    @field_validator("detail_json", mode="before")
    @classmethod
    def _parse_detail_json(cls, v: object) -> dict[str, Any] | None:
        """DB stores detail_json as a JSON-encoded Text column; deserialise it."""
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                parsed = _json.loads(v)
                return parsed if isinstance(parsed, dict) else None
            except (_json.JSONDecodeError, TypeError):
                return None
        return None

    model_config = {"from_attributes": True}


class SectionRewriteOut(BaseModel):
    id: str
    job_id: str
    section_id: str
    status: RewriteStatus
    rewritten_text: str | None
    model_name: str
    tokens_prompt: int
    tokens_completion: int
    duration_ms: int
    attempt_number: int
    review_status: str | None = None
    risk_findings: list[RiskFindingOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RewriteJobOut(BaseModel):
    id: str
    name: str | None = None
    document_id: str
    ruleset_id: str
    status: JobStatus
    created_by: str
    total_sections: int
    completed_sections: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    items: list[RewriteJobOut]
    total: int


class JobProgressUpdate(BaseModel):
    """Emitted over WebSocket during job execution."""

    job_id: str
    section_id: str
    status: RewriteStatus
    token: str | None = None          # streaming token during generation
    completed_sections: int = 0
    total_sections: int = 0
    error: str | None = None
    attempt: int = 1                  # retry counter; frontend resets buffer when > 1
