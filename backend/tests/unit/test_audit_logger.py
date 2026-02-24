"""Unit tests for app.services.audit.logger (hash chain integrity)."""
import hashlib
import json
import uuid

import pytest

from app.services.audit.logger import AuditLogger, verify_chain


pytestmark = pytest.mark.asyncio


async def _create_events(db_session, n: int = 3) -> list:
    """Helper: log n sequential audit events and return them ordered by id."""
    logger = AuditLogger(db_session)
    actor_id = uuid.uuid4()
    for i in range(n):
        await logger.log(
            event_type="test.event",
            actor_id=actor_id,
            resource_type="document",
            resource_id=uuid.uuid4(),
            details={"index": i},
        )
    await db_session.flush()
    # Return all test.event events ordered by creation
    from sqlalchemy import select
    from app.db.models.audit import AuditEvent
    result = await db_session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "test.event").order_by(AuditEvent.created_at)
    )
    return result.scalars().all()


# ─── Basic creation ───────────────────────────────────────────────────────────

async def test_log_creates_audit_event(db_session):
    events = await _create_events(db_session, n=1)
    assert len(events) == 1
    assert events[0].event_type == "test.event"


async def test_log_stores_event_hash(db_session):
    events = await _create_events(db_session, n=1)
    assert events[0].event_hash is not None
    assert len(events[0].event_hash) == 64  # SHA-256 hex


# ─── Hash chain linkage ───────────────────────────────────────────────────────

async def test_first_event_has_no_prev_hash(db_session):
    events = await _create_events(db_session, n=1)
    assert events[0].prev_hash is None or events[0].prev_hash == ""


async def test_second_event_prev_hash_matches_first_hash(db_session):
    events = await _create_events(db_session, n=2)
    assert events[1].prev_hash == events[0].event_hash


async def test_chain_is_linked_for_three_events(db_session):
    events = await _create_events(db_session, n=3)
    assert events[1].prev_hash == events[0].event_hash
    assert events[2].prev_hash == events[1].event_hash


# ─── verify_chain ─────────────────────────────────────────────────────────────

async def test_verify_chain_passes_on_valid_chain(db_session):
    events = await _create_events(db_session, n=3)
    result = await verify_chain(db_session)
    assert result.valid is True
    assert result.broken_at is None


async def test_verify_chain_fails_on_tampered_hash(db_session):
    events = await _create_events(db_session, n=2)
    # Tamper with the first event's hash directly
    events[0].event_hash = "deadbeef" * 8  # 64-char bogus hash
    await db_session.flush()
    result = await verify_chain(db_session)
    assert result.valid is False
    assert result.broken_at is not None


async def test_verify_chain_fails_on_broken_link(db_session):
    events = await _create_events(db_session, n=3)
    # Break the chain by changing the second event's prev_hash
    events[1].prev_hash = "0" * 64
    await db_session.flush()
    result = await verify_chain(db_session)
    assert result.valid is False


# ─── Event hash content ───────────────────────────────────────────────────────

async def test_event_hash_covers_key_fields(db_session):
    """The event_hash should cover at least actor_id + event_type + details."""
    events = await _create_events(db_session, n=1)
    ev = events[0]
    # Reconstruct the canonical payload that the logger should hash
    raw = json.dumps(
        {
            "event_type": ev.event_type,
            "actor_id": str(ev.actor_id),
            "resource_type": ev.resource_type,
            "resource_id": str(ev.resource_id),
            "details": ev.details,
        },
        sort_keys=True,
    )
    expected = hashlib.sha256(raw.encode()).hexdigest()
    assert ev.event_hash == expected
