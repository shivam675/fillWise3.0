"""RewriteJob and SectionRewrite database models."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models.document import Document, Section
    from app.db.models.review import Review
    from app.db.models.ruleset import Ruleset

from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RewriteStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RiskSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class RewriteJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    A batch rewrite job against a document using a specific ruleset.

    A job is the top-level unit of work. It schedules one SectionRewrite
    per eligible section and tracks overall status.
    """

    __tablename__ = "rewrite_jobs"

    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    ruleset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rulesets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status"),
        default=JobStatus.PENDING,
        nullable=False,
        index=True,
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_sections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_sections: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    document: Mapped[Document] = relationship("Document", back_populates="jobs")
    ruleset: Mapped[Ruleset] = relationship("Ruleset", back_populates="jobs")
    rewrites: Mapped[list[SectionRewrite]] = relationship(
        "SectionRewrite", back_populates="job", cascade="all, delete-orphan"
    )


class SectionRewrite(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    The result of rewriting a single document section.

    Stores the exact prompt used (for audit reproducibility), the raw
    LLM output, token counts, and timing.
    """

    __tablename__ = "section_rewrites"

    job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rewrite_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[RewriteStatus] = mapped_column(
        SAEnum(RewriteStatus, name="rewrite_status"),
        default=RewriteStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Immutable snapshot of the prompt used — auditable
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)

    rewritten_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tokens_prompt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_completion: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped[RewriteJob] = relationship("RewriteJob", back_populates="rewrites")
    section: Mapped[Section] = relationship("Section", back_populates="rewrites")
    risk_findings: Mapped[list[RiskFinding]] = relationship(
        "RiskFinding", back_populates="rewrite", cascade="all, delete-orphan"
    )
    review: Mapped[Review | None] = relationship(
        "Review", back_populates="rewrite", uselist=False
    )


class RiskFinding(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single risk finding raised against a section rewrite."""

    __tablename__ = "risk_findings"

    rewrite_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("section_rewrites.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    severity: Mapped[RiskSeverity] = mapped_column(
        SAEnum(RiskSeverity, name="risk_severity"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    detail_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    rewrite: Mapped[SectionRewrite] = relationship(
        "SectionRewrite", back_populates="risk_findings"
    )
