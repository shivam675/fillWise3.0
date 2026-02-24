"""Review, ReviewComment, and Review workflow models."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models.job import SectionRewrite

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EDITED = "edited"
    RERUN_REQUESTED = "rerun_requested"


class Review(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Human review record for a single SectionRewrite.

    One Review per SectionRewrite. The reviewer may provide edited_text
    which overrides the LLM output during assembly.
    """

    __tablename__ = "reviews"

    rewrite_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("section_rewrites.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    reviewer_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[ReviewStatus] = mapped_column(
        SAEnum(ReviewStatus, name="review_status"),
        default=ReviewStatus.PENDING,
        nullable=False,
        index=True,
    )
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    rewrite: Mapped[SectionRewrite] = relationship(
        "SectionRewrite", back_populates="review"
    )
    comments: Mapped[list[ReviewComment]] = relationship(
        "ReviewComment", back_populates="review", cascade="all, delete-orphan"
    )


class ReviewComment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A threaded comment on a specific diff hunk within a review."""

    __tablename__ = "review_comments"

    review_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_comment_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("review_comments.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    hunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(default=False, nullable=False)

    review: Mapped[Review] = relationship("Review", back_populates="comments")
    replies: Mapped[list["ReviewComment"]] = relationship(
        "ReviewComment",
        foreign_keys=[parent_comment_id],
        back_populates="parent",
    )
    parent: Mapped["ReviewComment | None"] = relationship(
        "ReviewComment",
        foreign_keys=[parent_comment_id],
        back_populates="replies",
        remote_side=lambda: [ReviewComment.id],
    )
