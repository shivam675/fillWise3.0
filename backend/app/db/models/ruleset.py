"""Ruleset, Rule, and RuleConflict database models."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models.job import RewriteJob

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Ruleset(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """
    A versioned collection of transformation rules.

    Rulesets are immutable once activated; a new version must be created
    to modify rules. The content_hash covers the full serialised rule set.
    """

    __tablename__ = "rulesets"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_rulesets_name_version"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    jurisdiction: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    rules_json: Mapped[str] = mapped_column(Text, nullable=False)

    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    conflicts: Mapped[list[RuleConflict]] = relationship(
        "RuleConflict", back_populates="ruleset", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[RewriteJob]] = relationship("RewriteJob", back_populates="ruleset")

    def __repr__(self) -> str:
        return f"<Ruleset {self.name} v{self.version}>"


class RuleConflict(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Records a detected conflict between two rules in a ruleset.

    Prevents activation of the ruleset until all conflicts are resolved.
    """

    __tablename__ = "rule_conflicts"

    ruleset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("rulesets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_a_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_b_id: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    ruleset: Mapped[Ruleset] = relationship("Ruleset", back_populates="conflicts")
