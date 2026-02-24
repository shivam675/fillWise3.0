"""Integration tests — authentication endpoints."""
import pytest

pytestmark = pytest.mark.asyncio


# ─── POST /auth/login ─────────────────────────────────────────────────────────

async def test_login_success(client, app):
    """Admin credentials created in app fixture → login must succeed."""
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "testadmin", "password": "Adm!nP@ssw0rd99"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password(client, app):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "testadmin", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


async def test_login_unknown_user(client, app):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "ghost", "password": "irrelevant"},
    )
    assert resp.status_code == 401


async def test_login_sets_csrf_cookie(client, app):
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "testadmin", "password": "Adm!nP@ssw0rd99"},
    )
    assert resp.status_code == 200
    assert "csrf_token" in resp.cookies


# ─── POST /auth/refresh ───────────────────────────────────────────────────────

async def test_refresh_returns_new_access_token(client, app):
    # First log in to get a refresh token
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "testadmin", "password": "Adm!nP@ssw0rd99"},
    )
    refresh_token = login.json()["refresh_token"]

    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_refresh_with_invalid_token_fails(client, app):
    resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not.a.valid.token"},
    )
    assert resp.status_code == 401


# ─── GET /auth/me ─────────────────────────────────────────────────────────────

async def test_me_requires_auth(client, app):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_returns_current_user(admin_client, app):
    resp = await admin_client.get("/api/v1/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == "testadmin"
    assert "password" not in body
    assert "hashed_password" not in body


# ─── POST /auth/change-password ───────────────────────────────────────────────

async def test_change_password_success(admin_client, app):
    resp = await admin_client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "Adm!nP@ssw0rd99",
            "new_password": "N3wStr0ngP@ss!",
        },
    )
    assert resp.status_code == 200


async def test_change_password_wrong_current(admin_client, app):
    resp = await admin_client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "wrongone",
            "new_password": "N3wStr0ng!",
        },
    )
    assert resp.status_code in (400, 401)


async def test_change_password_too_short(admin_client, app):
    resp = await admin_client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": "Adm!nP@ssw0rd99",
            "new_password": "short",
        },
    )
    assert resp.status_code == 422
