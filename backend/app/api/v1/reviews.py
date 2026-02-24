"""Review and approval API endpoints."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, ReviewerUser, get_db
from app.core.errors import ConflictError, ErrorCode, NotFoundError
from app.db.models.job import RiskSeverity, SectionRewrite
from app.db.models.review import Review, ReviewComment, ReviewStatus
from app.schemas.review import (
    AddCommentRequest,
    ReviewCommentOut,
    ReviewDecisionRequest,
    ReviewOut,
)
from app.services.audit.logger import AuditLogger
from app.services.review.diff import diff_to_json, generate_diff, json_to_diff

_log = structlog.get_logger(__name__)
router = APIRouter(prefix="/reviews", tags=["reviews"])


def _build_review_out(review: Review, rewrite: SectionRewrite | None = None) -> ReviewOut:
    hunks = json_to_diff(review.diff_json) if review.diff_json else []
    original_text: str | None = None
    rewritten_text: str | None = None
    risk_findings: list = []
    if rewrite is not None:
        original_text = rewrite.section.original_text if rewrite.section else None
        rewritten_text = rewrite.rewritten_text
        # Strip trailing LLM metadata from displayed text
        if rewritten_text:
            from app.services.llm.prompt_engine import _strip_trailing_metadata
            rewritten_text = _strip_trailing_metadata(rewritten_text, {})
        # Include risk findings from the rewrite
        if hasattr(rewrite, 'risk_findings') and rewrite.risk_findings:
            from app.schemas.review import RiskFindingOut
            risk_findings = [RiskFindingOut.model_validate(f) for f in rewrite.risk_findings]
    return ReviewOut(
        id=review.id,
        rewrite_id=review.rewrite_id,
        reviewer_id=review.reviewer_id,
        status=review.status,
        edited_text=review.edited_text,
        original_text=original_text,
        rewritten_text=rewritten_text,
        diff_hunks=[
            {"index": h.index, "operation": h.operation,
             "original": h.original, "rewritten": h.rewritten}
            for h in hunks
        ],
        risk_override_reason=review.risk_override_reason,
        risk_findings=risk_findings,
        comments=[ReviewCommentOut.model_validate(c) for c in (review.comments or [])],
        reviewed_at=review.updated_at if review.status != ReviewStatus.PENDING else None,
        created_at=review.created_at,
    )


@router.get(
    "/rewrite/{rewrite_id}",
    response_model=ReviewOut,
    summary="Get or create review for a section rewrite",
    dependencies=[ReviewerUser],
)
async def get_or_create_review(
    rewrite_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReviewOut:
    """
    Fetch the review for a rewrite, creating it if it doesn't exist yet.

    This is the entry point for the reviewer's diff view.
    """
    rewrite_result = await db.execute(
        select(SectionRewrite)
        .where(SectionRewrite.id == rewrite_id)
        .options(
            selectinload(SectionRewrite.section),
            selectinload(SectionRewrite.risk_findings)
        )
    )
    rewrite = rewrite_result.scalar_one_or_none()
    if rewrite is None:
        raise NotFoundError("SectionRewrite", rewrite_id)

    result = await db.execute(select(Review).where(Review.rewrite_id == rewrite_id))
    review: Review | None = result.scalar_one_or_none()

    if review is None:
        # Create the review record with a precomputed diff
        original = rewrite.section.original_text if rewrite.section else ""
        rewritten = rewrite.rewritten_text or ""
        diff_hunks = generate_diff(original, rewritten)

        review = Review(
            rewrite_id=rewrite_id,
            reviewer_id=current_user.id,
            status=ReviewStatus.PENDING,
            diff_json=diff_to_json(diff_hunks),
        )
        db.add(review)
        await db.flush()
        await db.refresh(review, ["comments"])
        await db.commit()

    else:
        await db.refresh(review, ["comments"])

    return _build_review_out(review, rewrite)


@router.post(
    "/{review_id}/decide",
    response_model=ReviewOut,
    summary="Submit a review decision",
    dependencies=[ReviewerUser],
)
async def decide_review(
    review_id: str,
    body: ReviewDecisionRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReviewOut:
    """
    Submit an approve/reject/edit decision on a review.

    If the rewrite has CRITICAL risk findings and status is APPROVED,
    a risk_override_reason must be provided.
    """
    _log.info("Processing review decision", review_id=review_id, decision_status=body.status.value)
    
    review = await db.get(Review, review_id)
    if review is None:
        raise NotFoundError("Review", review_id)

    _log.info("Current review state", review_id=review_id, current_status=review.status.value)

    if review.status not in (ReviewStatus.PENDING, ReviewStatus.RERUN_REQUESTED):
        _log.warning(
            "Attempt to modify already decided review", 
            review_id=review_id, 
            current_status=review.status.value,
            requested_status=body.status.value,
            user_id=current_user.id
        )
        raise ConflictError(
            ErrorCode.REVIEW_ALREADY_DECIDED,
            f"Review is already in status '{review.status}' and cannot be changed.",
        )

    # Enforce risk override reason for critical findings
    if body.status == ReviewStatus.APPROVED:
        rw_result = await db.execute(
            select(SectionRewrite)
            .where(SectionRewrite.id == review.rewrite_id)
            .options(selectinload(SectionRewrite.risk_findings))
        )
        rewrite_check = rw_result.scalar_one_or_none()
        if rewrite_check and rewrite_check.risk_findings:
            critical = [f for f in rewrite_check.risk_findings 
                       if f.severity in (RiskSeverity.CRITICAL, RiskSeverity.HIGH)]
            if critical and not body.risk_override_reason:
                raise ConflictError(
                    ErrorCode.REVIEW_REWRITE_PENDING,
                    f"This rewrite has {len(critical)} CRITICAL/HIGH risk finding(s). "
                    "Provide a risk_override_reason to override.",
                )

    review.status = body.status
    review.reviewer_id = current_user.id
    review.risk_override_reason = body.risk_override_reason
    
    _log.info(
        "Review status updated successfully", 
        review_id=review_id, 
        new_status=body.status.value,
        reviewer_id=current_user.id,
        has_risk_override=bool(body.risk_override_reason)
    )

    if body.status == ReviewStatus.EDITED and body.edited_text:
        review.edited_text = body.edited_text
        # Recompute diff against edited text
        rewrite_result2 = await db.execute(
            select(SectionRewrite)
            .where(SectionRewrite.id == review.rewrite_id)
            .options(selectinload(SectionRewrite.section))
        )
        rewrite_for_diff = rewrite_result2.scalar_one_or_none()
        if rewrite_for_diff and rewrite_for_diff.section:
            diff_hunks = generate_diff(rewrite_for_diff.section.original_text, body.edited_text)
            review.diff_json = diff_to_json(diff_hunks)

    audit = AuditLogger(db)
    await audit.log(
        event_type=f"review.{body.status.value}",
        actor_id=current_user.id,
        actor_username=current_user.username,
        entity_type="Review",
        entity_id=review.id,
        payload={"status": body.status.value, "rewrite_id": review.rewrite_id},
    )
    await db.commit()
    await db.refresh(review, ["comments"])

    # Load rewrite with risk findings for the response
    rewrite_response_result = await db.execute(
        select(SectionRewrite)
        .where(SectionRewrite.id == review.rewrite_id)
        .options(
            selectinload(SectionRewrite.section),
            selectinload(SectionRewrite.risk_findings)
        )
    )
    rewrite_for_response = rewrite_response_result.scalar_one_or_none()

    return _build_review_out(review, rewrite_for_response)


@router.post(
    "/{review_id}/comments",
    response_model=ReviewCommentOut,
    status_code=201,
    summary="Add a comment to a review",
    dependencies=[ReviewerUser],
)
async def add_comment(
    review_id: str,
    body: AddCommentRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReviewCommentOut:
    review = await db.get(Review, review_id)
    if review is None:
        raise NotFoundError("Review", review_id)

    comment = ReviewComment(
        review_id=review_id,
        parent_comment_id=body.parent_comment_id,
        author_id=current_user.id,
        hunk_index=body.hunk_index,
        body=body.body,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return ReviewCommentOut.model_validate(comment)
