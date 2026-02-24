"""Integration tests — audit endpoints."""
import pytest

pytestmark = pytest.mark.asyncio


# ─── GET /audit ───────────────────────────────────────────────────────────────

async def test_list_audit_events_returns_200(admin_client, app):
    resp = await admin_client.get("/api/v1/audit/")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)


async def test_list_audit_requires_auth(client, app):
    resp = await client.get("/api/v1/audit/")
    assert resp.status_code == 401


async def test_list_audit_requires_admin(client, app, admin_client):
    # Create a Reviewer
    import uuid
    uname = f"rev_{uuid.uuid4().hex[:8]}"
    await admin_client.post(
        "/api/v1/admin/users",
        json={"username": uname, "password": "ReviewerP@ss1!", "role": "reviewer"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": uname, "password": "ReviewerP@ss1!"},
    )
    token = login.json()["access_token"]
    resp = await client.get(
        "/api/v1/audit/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_audit_events_logged_after_login(admin_client, app):
    """Logging in should produce at least one audit event."""
    resp = await admin_client.get("/api/v1/audit/")
    assert resp.json()["total"] > 0


async def test_audit_filter_by_event_type(admin_client, app):
    resp = await admin_client.get("/api/v1/audit/?event_type=auth.login")
    assert resp.status_code == 200
    items = resp.json()["items"]
    for item in items:
        assert item["event_type"] == "auth.login"


async def test_audit_pagination(admin_client, app):
    resp = await admin_client.get("/api/v1/audit/?limit=1&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) <= 1


# ─── GET /audit/verify ────────────────────────────────────────────────────────

async def test_verify_chain_returns_200(admin_client, app):
    resp = await admin_client.get("/api/v1/audit/verify")
    assert resp.status_code == 200
    body = resp.json()
    assert "valid" in body
    assert isinstance(body["valid"], bool)


async def test_verify_chain_valid_on_fresh_db(admin_client, app):
    resp = await admin_client.get("/api/v1/audit/verify")
    assert resp.json()["valid"] is True


async def test_verify_chain_requires_admin(client, app, admin_client):
    import uuid
    uname = f"viewer_{uuid.uuid4().hex[:8]}"
    await admin_client.post(
        "/api/v1/admin/users",
        json={"username": uname, "password": "ViewerP@ss1!", "role": "viewer"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": uname, "password": "ViewerP@ss1!"},
    )
    token = login.json()["access_token"]
    resp = await client.get(
        "/api/v1/audit/verify",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
