"""
Immutable audit event model.

Events form a hash chain: each event records the SHA-256 hash of the
previous event. This makes it computationally infeasible to silently
delete or modify historical records.

The chain can be verified via AuditService.verify_chain().
"""

from __future__ import annotations

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Single immutable audit event."""

    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("event_hash", name="uq_audit_event_hash"),
        Index("ix_audit_events_actor_entity", "actor_id", "entity_type", "entity_id"),
    )

    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Hash of this event (covers all fields except event_hash itself)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Hash of the previous event in the chain; null for the genesis event
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    def __repr__(self) -> str:
        return f"<AuditEvent {self.event_type} [{self.actor_username}]>"
