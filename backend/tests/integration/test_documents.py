"""Integration tests — document endpoints."""
import io
import uuid

import pytest

pytestmark = pytest.mark.asyncio

# Minimal 1-page PDF bytes (valid enough for header detection)
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

_MINIMAL_DOCX_CONTENT = b"PK\x03\x04"  # DOCX is a ZIP — just needs the magic bytes for MIME check


def _pdf_upload_files():
    return {"file": ("test_contract.pdf", io.BytesIO(_MINIMAL_PDF), "application/pdf")}


# ─── POST /documents ──────────────────────────────────────────────────────────

async def test_upload_pdf_returns_201(admin_client, app):
    resp = await admin_client.post("/api/v1/documents/", files=_pdf_upload_files())
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["filename"] == "test_contract.pdf"
    assert body["status"] in ("pending", "extracting")


async def test_upload_creates_document_record(admin_client, app):
    resp = await admin_client.post("/api/v1/documents/", files=_pdf_upload_files())
    doc_id = resp.json()["id"]
    get_resp = await admin_client.get(f"/api/v1/documents/{doc_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == doc_id


async def test_upload_rejects_wrong_mime(admin_client, app):
    files = {"file": ("evil.exe", io.BytesIO(b"\x4d\x5a\x90\x00"), "application/octet-stream")}
    resp = await admin_client.post("/api/v1/documents/", files=files)
    assert resp.status_code == 422


async def test_upload_rejects_oversized_file(admin_client, app):
    """50 MB of zeros should exceed the upload limit."""
    big = io.BytesIO(b"\x00" * (50 * 1024 * 1024))
    files = {"file": ("huge.pdf", big, "application/pdf")}
    resp = await admin_client.post("/api/v1/documents/", files=files)
    # Either 413 or 422 depending on implementation
    assert resp.status_code in (413, 422)


async def test_upload_requires_auth(client, app):
    resp = await client.post("/api/v1/documents/", files=_pdf_upload_files())
    assert resp.status_code == 401


# ─── GET /documents ───────────────────────────────────────────────────────────

async def test_list_documents_returns_200(admin_client, app):
    resp = await admin_client.get("/api/v1/documents/")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)


async def test_list_documents_includes_uploaded(admin_client, app):
    upload = await admin_client.post("/api/v1/documents/", files=_pdf_upload_files())
    doc_id = upload.json()["id"]
    resp = await admin_client.get("/api/v1/documents/")
    ids = [d["id"] for d in resp.json()["items"]]
    assert doc_id in ids


async def test_list_requires_auth(client, app):
    resp = await client.get("/api/v1/documents/")
    assert resp.status_code == 401


# ─── GET /documents/:id ───────────────────────────────────────────────────────

async def test_get_document_returns_200(admin_client, app):
    upload = await admin_client.post("/api/v1/documents/", files=_pdf_upload_files())
    doc_id = upload.json()["id"]
    resp = await admin_client.get(f"/api/v1/documents/{doc_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == doc_id


async def test_get_nonexistent_document_returns_404(admin_client, app):
    fake_id = str(uuid.uuid4())
    resp = await admin_client.get(f"/api/v1/documents/{fake_id}")
    assert resp.status_code == 404


# ─── DELETE /documents/:id ────────────────────────────────────────────────────

async def test_delete_document_returns_204(admin_client, app):
    upload = await admin_client.post("/api/v1/documents/", files=_pdf_upload_files())
    doc_id = upload.json()["id"]
    del_resp = await admin_client.delete(f"/api/v1/documents/{doc_id}")
    assert del_resp.status_code == 204


async def test_delete_removes_document(admin_client, app):
    upload = await admin_client.post("/api/v1/documents/", files=_pdf_upload_files())
    doc_id = upload.json()["id"]
    await admin_client.delete(f"/api/v1/documents/{doc_id}")
    get_resp = await admin_client.get(f"/api/v1/documents/{doc_id}")
    assert get_resp.status_code == 404


async def test_delete_nonexistent_returns_404(admin_client, app):
    resp = await admin_client.delete(f"/api/v1/documents/{uuid.uuid4()}")
    assert resp.status_code == 404


# ─── GET /documents/:id/sections ─────────────────────────────────────────────

async def test_sections_requires_auth(client, app):
    resp = await client.get(f"/api/v1/documents/{uuid.uuid4()}/sections")
    assert resp.status_code == 401


async def test_sections_returns_list(admin_client, app):
    upload = await admin_client.post("/api/v1/documents/", files=_pdf_upload_files())
    doc_id = upload.json()["id"]
    resp = await admin_client.get(f"/api/v1/documents/{doc_id}/sections")
    # Document is pending so may have no sections yet, but endpoint should succeed
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
