"""Job and SectionRewrite schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models.job import JobStatus, RewriteStatus, RiskSeverity


class CreateJobRequest(BaseModel):
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
    risk_findings: list[RiskFindingOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RewriteJobOut(BaseModel):
    id: str
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
