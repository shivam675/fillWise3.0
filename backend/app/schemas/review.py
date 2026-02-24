"""Review and comment schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models.review import ReviewStatus


class RiskFindingOut(BaseModel):
    id: str
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW | INFO
    category: str
    description: str
    score: float
    detail_json: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewDecisionRequest(BaseModel):
    status: ReviewStatus = Field(..., description="APPROVED | REJECTED | EDITED | RERUN_REQUESTED")
    edited_text: str | None = Field(
        default=None,
        description="Required when status=EDITED. The reviewer's corrected text.",
    )
    risk_override_reason: str | None = Field(
        default=None,
        description="Required when approving a rewrite with CRITICAL risk findings.",
    )

    def model_post_init(self, __context: object) -> None:
        if self.status == ReviewStatus.EDITED and not self.edited_text:
            raise ValueError("edited_text is required when status is EDITED")


class AddCommentRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)
    hunk_index: int | None = Field(default=None, ge=0)
    parent_comment_id: str | None = None


class ReviewCommentOut(BaseModel):
    id: str
    review_id: str
    parent_comment_id: str | None
    author_id: str
    hunk_index: int | None
    body: str
    is_resolved: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class DiffHunk(BaseModel):
    """A single diff hunk between original and rewritten text."""

    index: int
    operation: str  # "equal" | "insert" | "delete" | "replace"
    original: str
    rewritten: str


class ReviewOut(BaseModel):
    id: str
    rewrite_id: str
    reviewer_id: str
    status: ReviewStatus
    edited_text: str | None
    original_text: str | None
    rewritten_text: str | None
    diff_hunks: list[DiffHunk] = Field(default_factory=list)
    risk_override_reason: str | None
    risk_findings: list[RiskFindingOut] = Field(default_factory=list)
    comments: list[ReviewCommentOut] = Field(default_factory=list)
    reviewed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
