"""
Shared pytest fixtures for FillWise backend tests.

Provides:
  - async SQLite in-memory database (per-test isolation)
  - authenticated TestClient (admin and regular users)
  - mock Ollama client (no real LLM calls)
"""
from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app


# ─── Settings override ────────────────────────────────────────────────────────

TEST_SETTINGS = Settings(
    database_url="sqlite+aiosqlite:///:memory:",
    jwt_secret="test-secret-key-not-for-production-at-all",
    admin_password="TestAdmin@2024!",
    debug=True,
    run_migrations_on_startup=False,
    cors_origins=["http://localhost:5173"],
    log_json=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ─── Database ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create an async in-memory SQLite engine per test function."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session that rolls back after each test."""
    factory = async_sessionmaker(
        db_engine, expire_on_commit=False, autoflush=False
    )
    async with factory() as session:
        yield session
        await session.rollback()


# ─── App & HTTP client ────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="function")
async def app(db_engine):
    """Create FastAPI test app with overridden DB dependency."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            yield session

    # Seed roles before tests run.
    async with factory() as session:
        from app.db.models.user import Role, RoleEnum
        for role_name in RoleEnum:
            from sqlalchemy import select
            result = await session.execute(
                select(Role).where(Role.name == role_name.value)
            )
            if not result.scalar_one_or_none():
                session.add(Role(name=role_name.value, description=role_name.value))
        await session.commit()

    app_ = create_app(settings=TEST_SETTINGS)
    app_.dependency_overrides[get_db] = override_get_db
    return app_


@pytest_asyncio.fixture(scope="function")
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Unauthenticated async HTTP client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


@pytest_asyncio.fixture(scope="function")
async def admin_client(client: AsyncClient, db_session: AsyncSession) -> AsyncClient:
    """
    HTTP client pre-authenticated as the seeded admin user.
    Creates the admin user if it doesn't exist yet.
    """
    from app.core.security import hash_password
    from app.db.models.user import User, Role, RoleEnum
    from sqlalchemy import select

    # Get admin role
    role = (
        await db_session.execute(
            select(Role).where(Role.name == RoleEnum.ADMIN.value)
        )
    ).scalar_one()

    # Create admin user
    admin = User(
        username="testadmin",
        password_hash=hash_password("TestAdmin@2024!"),
        role_id=role.id,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "testadmin", "password": "TestAdmin@2024!"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    csrf = resp.cookies.get("csrf_token", "test-csrf")

    client.headers.update(
        {"Authorization": f"Bearer {token}", "X-CSRF-Token": csrf}
    )
    return client


# ─── Mock Ollama ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_ollama():
    """Patch OllamaClient so no real HTTP calls are made."""

    async def fake_stream(*_args: Any, **_kwargs: Any):
        for word in ["This", " is", " a", " test", " rewrite."]:
            yield word

    mock = MagicMock()
    mock.stream_completion = fake_stream
    mock.health_check = AsyncMock(return_value=True)

    with patch("app.services.llm.client.OllamaClient", return_value=mock):
        with patch("app.services.llm.orchestrator.OllamaClient", return_value=mock):
            yield mock
