"""Integration tests — rewrite-job endpoints."""
import io
import uuid

import pytest

pytestmark = pytest.mark.asyncio

_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF\n"
)


async def _upload_doc(admin_client) -> str:
    resp = await admin_client.post(
        "/api/v1/documents/",
        files={"file": ("c.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _upload_ruleset(admin_client) -> str:
    yaml_content = b"""schema_version: "1.0"
name: test_ruleset
version: "1.0.0"
description: Test
jurisdiction: null
rules:
  - id: T-001
    section_types: [clause]
    instruction: Rewrite in plain English.
    priority: 10
    preserve_numbers: true
    preserve_dates: true
    preserve_parties: true
    tags: []
"""
    resp = await admin_client.post(
        "/api/v1/rulesets/",
        files={"file": ("test.yaml", io.BytesIO(yaml_content), "application/x-yaml")},
    )
    assert resp.status_code == 201
    return resp.json()["id"]


# ─── POST /jobs ───────────────────────────────────────────────────────────────

async def test_create_job_requires_auth(client, app):
    resp = await client.post(
        "/api/v1/jobs/",
        json={"document_id": str(uuid.uuid4()), "ruleset_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 401


async def test_create_job_nonexistent_document(admin_client, app):
    ruleset_id = await _upload_ruleset(admin_client)
    resp = await admin_client.post(
        "/api/v1/jobs/",
        json={"document_id": str(uuid.uuid4()), "ruleset_id": ruleset_id},
    )
    assert resp.status_code == 404


async def test_create_job_nonexistent_ruleset(admin_client, app):
    doc_id = await _upload_doc(admin_client)
    resp = await admin_client.post(
        "/api/v1/jobs/",
        json={"document_id": doc_id, "ruleset_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


async def test_create_job_document_not_mapped(admin_client, app):
    """Document must be in MAPPED status to start a job."""
    doc_id = await _upload_doc(admin_client)  # status is 'pending' not 'mapped'
    ruleset_id = await _upload_ruleset(admin_client)
    resp = await admin_client.post(
        "/api/v1/jobs/",
        json={"document_id": doc_id, "ruleset_id": ruleset_id},
    )
    assert resp.status_code in (400, 409)


# ─── GET /jobs ────────────────────────────────────────────────────────────────

async def test_list_jobs_returns_200(admin_client, app):
    resp = await admin_client.get("/api/v1/jobs/")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body or isinstance(body, list)


async def test_list_jobs_requires_auth(client, app):
    resp = await client.get("/api/v1/jobs/")
    assert resp.status_code == 401


# ─── GET /jobs/:id ────────────────────────────────────────────────────────────

async def test_get_nonexistent_job_returns_404(admin_client, app):
    resp = await admin_client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404


# ─── GET /jobs/:id/rewrites ───────────────────────────────────────────────────

async def test_get_rewrites_nonexistent_job_returns_404(admin_client, app):
    resp = await admin_client.get(f"/api/v1/jobs/{uuid.uuid4()}/rewrites")
    assert resp.status_code == 404
