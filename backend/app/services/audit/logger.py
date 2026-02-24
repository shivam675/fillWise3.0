"""
Immutable audit logger.

Every event is SHA-256 hashed, including the hash of the immediately
preceding event. This forms a cryptographic hash chain that makes
tampering with historical records detectable.

The chain is linear (single sequence). Thread safety is ensured by
serialising writes via an asyncio lock.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit import AuditEvent

_log = structlog.get_logger(__name__)

_LOCK = asyncio.Lock()


def _compute_event_hash(
    event_type: str,
    actor_id: str | None,
    entity_type: str | None,
    entity_id: str | None,
    payload_json: str | None,
    created_at: datetime,
    prev_hash: str | None,
) -> str:
    """Compute the SHA-256 hash for an audit event."""
    components = {
        "event_type": event_type,
        "actor_id": actor_id or "",
        "entity_type": entity_type or "",
        "entity_id": entity_id or "",
        "payload_json": payload_json or "",
        "created_at": created_at.isoformat(),
        "prev_hash": prev_hash or "",
    }
    canonical = json.dumps(components, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


class AuditLogger:
    """
    Service for writing immutable audit events.

    Usage:
        logger = AuditLogger(db)
        await logger.log(
            event_type="document.uploaded",
            actor=current_user,
            entity_type="Document",
            entity_id=doc.id,
            payload={"filename": doc.original_filename},
        )
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def log(
        self,
        event_type: str,
        actor_id: str | None = None,
        actor_username: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        correlation_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """
        Write a single audit event to the database.

        The lock ensures prev_hash is read and written atomically even
        under concurrent requests, preserving chain integrity.
        """
        async with _LOCK:
            prev_hash = await self._get_last_hash()
            created_at = datetime.now(UTC)
            payload_json = json.dumps(payload, sort_keys=True) if payload else None

            event_hash = _compute_event_hash(
                event_type=event_type,
                actor_id=actor_id,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
                created_at=created_at,
                prev_hash=prev_hash,
            )

            event = AuditEvent(
                event_type=event_type,
                actor_id=actor_id,
                actor_username=actor_username,
                entity_type=entity_type,
                entity_id=entity_id,
                correlation_id=correlation_id,
                payload_json=payload_json,
                event_hash=event_hash,
                prev_hash=prev_hash,
                created_at=created_at,
            )
            self._db.add(event)
            await self._db.flush()

            _log.debug(
                "audit_event_written",
                event_type=event_type,
                actor_id=actor_id,
                entity_id=entity_id,
                event_hash=event_hash,
            )
            return event

    async def _get_last_hash(self) -> str | None:
        """Fetch the event_hash of the most recently written audit event."""
        result = await self._db.execute(
            select(AuditEvent.event_hash)
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def verify_chain(db: AsyncSession) -> tuple[bool, str | None]:
        """
        Verify the integrity of the audit hash chain.

        Returns:
            (True, None) if chain is intact.
            (False, event_id) of the first event where the chain is broken.
        """
        result = await db.execute(
            select(AuditEvent).order_by(AuditEvent.created_at.asc())
        )
        events: list[AuditEvent] = list(result.scalars().all())

        prev_hash: str | None = None
        for event in events:
            expected = _compute_event_hash(
                event_type=event.event_type,
                actor_id=event.actor_id,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                payload_json=event.payload_json,
                created_at=event.created_at,
                prev_hash=prev_hash,
            )
            if expected != event.event_hash:
                _log.error(
                    "audit_chain_broken",
                    event_id=event.id,
                    expected_hash=expected,
                    stored_hash=event.event_hash,
                )
                return False, event.id

            prev_hash = event.event_hash

        return True, None
