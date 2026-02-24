"""Integration tests — admin endpoints (user management)."""
import uuid

import pytest

pytestmark = pytest.mark.asyncio


# ─── GET /admin/users ─────────────────────────────────────────────────────────

async def test_list_users_returns_200(admin_client, app):
    resp = await admin_client.get("/api/v1/admin/users")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_list_users_includes_admin(admin_client, app):
    resp = await admin_client.get("/api/v1/admin/users")
    usernames = [u["username"] for u in resp.json()]
    assert "testadmin" in usernames


async def test_list_users_requires_auth(client, app):
    resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 401


# ─── POST /admin/users ────────────────────────────────────────────────────────

async def test_create_user_returns_201(admin_client, app):
    resp = await admin_client.post(
        "/api/v1/admin/users",
        json={
            "username": f"newuser_{uuid.uuid4().hex[:8]}",
            "password": "SecureP@ss1!",
            "email": "new@example.com",
            "role": "reviewer",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert "hashed_password" not in body


async def test_create_user_duplicate_username(admin_client, app):
    uname = f"dup_{uuid.uuid4().hex[:8]}"
    await admin_client.post(
        "/api/v1/admin/users",
        json={"username": uname, "password": "SecureP@ss1!", "role": "viewer"},
    )
    resp = await admin_client.post(
        "/api/v1/admin/users",
        json={"username": uname, "password": "AnotherP@ss2!", "role": "viewer"},
    )
    assert resp.status_code == 409


async def test_create_user_invalid_role(admin_client, app):
    resp = await admin_client.post(
        "/api/v1/admin/users",
        json={
            "username": "badroluser",
            "password": "SecureP@ss1!",
            "role": "superroot",
        },
    )
    assert resp.status_code == 422


async def test_create_user_weak_password(admin_client, app):
    resp = await admin_client.post(
        "/api/v1/admin/users",
        json={
            "username": "weakpassuser",
            "password": "abc",
            "role": "viewer",
        },
    )
    assert resp.status_code == 422


async def test_create_user_requires_admin_role(client, app, admin_client):
    # First create a non-admin user
    uname = f"editor_{uuid.uuid4().hex[:8]}"
    await admin_client.post(
        "/api/v1/admin/users",
        json={"username": uname, "password": "EditorP@ss1!", "role": "editor"},
    )
    # Log in as editor
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": uname, "password": "EditorP@ss1!"},
    )
    editor_token = login.json()["access_token"]
    from httpx import AsyncClient
    from app.main import create_app
    # Re-use the same transport but with editor token
    resp = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {editor_token}"},
    )
    assert resp.status_code == 403


# ─── DELETE /admin/users/:id ──────────────────────────────────────────────────

async def test_delete_user_returns_204(admin_client, app):
    create = await admin_client.post(
        "/api/v1/admin/users",
        json={"username": f"todel_{uuid.uuid4().hex[:8]}", "password": "ToDelP@ss1!", "role": "viewer"},
    )
    user_id = create.json()["id"]
    resp = await admin_client.delete(f"/api/v1/admin/users/{user_id}")
    assert resp.status_code == 204


async def test_delete_nonexistent_user_returns_404(admin_client, app):
    resp = await admin_client.delete(f"/api/v1/admin/users/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_admin_cannot_delete_self(admin_client, app):
    me_resp = await admin_client.get("/api/v1/auth/me")
    my_id = me_resp.json()["id"]
    resp = await admin_client.delete(f"/api/v1/admin/users/{my_id}")
    assert resp.status_code in (400, 403, 409)


# ─── PATCH /admin/users/:id ───────────────────────────────────────────────────

async def test_update_user_role(admin_client, app):
    create = await admin_client.post(
        "/api/v1/admin/users",
        json={"username": f"rolechange_{uuid.uuid4().hex[:8]}", "password": "Ch@ngeP@ss1!", "role": "viewer"},
    )
    user_id = create.json()["id"]
    resp = await admin_client.patch(
        f"/api/v1/admin/users/{user_id}",
        json={"role": "editor"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "editor"
