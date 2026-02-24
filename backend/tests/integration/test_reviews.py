"""Integration tests — review endpoints."""
import uuid

import pytest
import pytest_asyncio

from app.db.models.rewrite import RewriteJob, SectionRewrite, RewriteStatus
from app.db.models.risk import RiskFinding, RiskSeverity as DBRiskSeverity
from app.db.models.document import Document, DocumentStatus
from app.db.models.section import Section, SectionType
from app.db.models.ruleset import Ruleset

pytestmark = pytest.mark.asyncio


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _seed_completed_rewrite(db_session, owner_id: uuid.UUID) -> uuid.UUID:
    """Insert minimal DB rows so that a SectionRewrite exists with status COMPLETED."""
    # Document
    doc = Document(
        id=uuid.uuid4(),
        owner_id=owner_id,
        filename="seed.pdf",
        file_path="/tmp/seed.pdf",
        file_size=1024,
        mime_type="application/pdf",
        status=DocumentStatus.MAPPED,
    )
    db_session.add(doc)

    # Section
    sec = Section(
        id=uuid.uuid4(),
        document_id=doc.id,
        sequence=1,
        section_type=SectionType.CLAUSE,
        heading=None,
        text="The vendor shall deliver 100 units by 31 March.",
        char_start=0,
        char_end=47,
        page_number=1,
    )
    db_session.add(sec)

    # Ruleset (bare minimum)
    rs = Ruleset(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name="seed_ruleset",
        version="1.0.0",
        rules_hash="aabbcc",
        is_active=True,
        rules_data=[],
    )
    db_session.add(rs)

    # RewriteJob
    job = RewriteJob(
        id=uuid.uuid4(),
        document_id=doc.id,
        ruleset_id=rs.id,
        created_by=owner_id,
        status="completed",
        total_sections=1,
        completed_sections=1,
    )
    db_session.add(job)

    # SectionRewrite
    rewrite = SectionRewrite(
        id=uuid.uuid4(),
        job_id=job.id,
        section_id=sec.id,
        original_text="The vendor shall deliver 100 units by 31 March.",
        rewritten_text="The vendor must deliver 100 units by 31 March.",
        status=RewriteStatus.COMPLETED,
        diff_json="[]",
        prompt_hash="deadbeef",
        audit_metadata={},
    )
    db_session.add(rewrite)
    await db_session.flush()
    return rewrite.id


# ─── GET /reviews/{rewrite_id} (get-or-create) ───────────────────────────────

async def test_get_or_create_review_creates_record(admin_client, app, db_session):
    from app.db.models.user import User
    from sqlalchemy import select
    owner = (await db_session.execute(
        select(User).where(User.username == "testadmin")
    )).scalar_one()
    rewrite_id = await _seed_completed_rewrite(db_session, owner.id)

    resp = await admin_client.get(f"/api/v1/reviews/{rewrite_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    assert body["rewrite_id"] == str(rewrite_id)


async def test_get_or_create_review_is_idempotent(admin_client, app, db_session):
    from app.db.models.user import User
    from sqlalchemy import select
    owner = (await db_session.execute(
        select(User).where(User.username == "testadmin")
    )).scalar_one()
    rewrite_id = await _seed_completed_rewrite(db_session, owner.id)

    resp1 = await admin_client.get(f"/api/v1/reviews/{rewrite_id}")
    resp2 = await admin_client.get(f"/api/v1/reviews/{rewrite_id}")
    assert resp1.json()["id"] == resp2.json()["id"]


async def test_get_review_nonexistent_rewrite_404(admin_client, app):
    resp = await admin_client.get(f"/api/v1/reviews/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_get_review_requires_auth(client, app):
    resp = await client.get(f"/api/v1/reviews/{uuid.uuid4()}")
    assert resp.status_code == 401


# ─── POST /reviews/{review_id}/decide ────────────────────────────────────────

async def _get_review_id(admin_client, app, db_session) -> uuid.UUID:
    from app.db.models.user import User
    from sqlalchemy import select
    owner = (await db_session.execute(
        select(User).where(User.username == "testadmin")
    )).scalar_one()
    rewrite_id = await _seed_completed_rewrite(db_session, owner.id)
    resp = await admin_client.get(f"/api/v1/reviews/{rewrite_id}")
    return uuid.UUID(resp.json()["id"])


async def test_approve_review_sets_approved_status(admin_client, app, db_session):
    review_id = await _get_review_id(admin_client, app, db_session)
    resp = await admin_client.post(
        f"/api/v1/reviews/{review_id}/decide",
        json={"decision": "approved"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


async def test_reject_review_sets_rejected_status(admin_client, app, db_session):
    review_id = await _get_review_id(admin_client, app, db_session)
    resp = await admin_client.post(
        f"/api/v1/reviews/{review_id}/decide",
        json={"decision": "rejected", "comment": "Not acceptable."},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


async def test_edit_review_saves_edited_text(admin_client, app, db_session):
    review_id = await _get_review_id(admin_client, app, db_session)
    resp = await admin_client.post(
        f"/api/v1/reviews/{review_id}/decide",
        json={
            "decision": "edited",
            "edited_text": "The vendor must supply 100 units by 31 March.",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "edited"
    assert body["edited_text"] == "The vendor must supply 100 units by 31 March."


async def test_critical_risk_requires_override(admin_client, app, db_session):
    """Approving a rewrite that has CRITICAL risk findings without an override_reason
    should be rejected with 422."""
    from app.db.models.user import User
    from sqlalchemy import select
    owner = (await db_session.execute(
        select(User).where(User.username == "testadmin")
    )).scalar_one()
    rewrite_id = await _seed_completed_rewrite(db_session, owner.id)

    # Get the review
    get_resp = await admin_client.get(f"/api/v1/reviews/{rewrite_id}")
    review_id = uuid.UUID(get_resp.json()["id"])

    # Inject a CRITICAL risk finding into the seeded section_rewrite
    from app.db.models.risk import RiskFinding
    finding = RiskFinding(
        id=uuid.uuid4(),
        section_rewrite_id=rewrite_id,
        check_name="numeric_drift",
        severity=DBRiskSeverity.CRITICAL,
        description="Number removed",
        original_snippet="100 units",
        rewritten_snippet="",
    )
    db_session.add(finding)
    await db_session.flush()

    resp = await admin_client.post(
        f"/api/v1/reviews/{review_id}/decide",
        json={"decision": "approved"},  # no override_reason
    )
    assert resp.status_code == 422


# ─── POST /reviews/{review_id}/comments ──────────────────────────────────────

async def test_add_comment_returns_201(admin_client, app, db_session):
    review_id = await _get_review_id(admin_client, app, db_session)
    resp = await admin_client.post(
        f"/api/v1/reviews/{review_id}/comments",
        json={"body": "Please fix the date reference."},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["body"] == "Please fix the date reference."


async def test_list_comments_returns_posted_comment(admin_client, app, db_session):
    review_id = await _get_review_id(admin_client, app, db_session)
    await admin_client.post(
        f"/api/v1/reviews/{review_id}/comments",
        json={"body": "Looks good overall."},
    )
    resp = await admin_client.get(f"/api/v1/reviews/{review_id}/comments")
    assert resp.status_code == 200
    bodies = [c["body"] for c in resp.json()]
    assert "Looks good overall." in bodies
