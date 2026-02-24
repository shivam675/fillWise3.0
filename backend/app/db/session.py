"""Async SQLAlchemy session factory and dependency."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _build_engine_kwargs(settings: Settings) -> dict[str, Any]:
    """
    Return engine creation kwargs appropriate for the configured database.

    SQLite does not support pool_size / max_overflow; PostgreSQL does.
    """
    url = str(settings.database_url)
    base: dict[str, Any] = {"echo": settings.db_echo}

    if "sqlite" in url:
        # SQLite is single-writer; pool class is StaticPool for testing
        base["connect_args"] = {"check_same_thread": False}
    else:
        base["pool_size"] = settings.db_pool_size
        base["max_overflow"] = settings.db_max_overflow
        base["pool_pre_ping"] = True

    return base


def create_engine(settings: Settings | None = None) -> AsyncEngine:
    """Create and return the global async engine."""
    global _engine
    if _engine is None:
        cfg = settings or get_settings()
        _engine = create_async_engine(
            str(cfg.database_url),
            **_build_engine_kwargs(cfg),
        )
    return _engine


def get_session_factory(settings: Settings | None = None) -> async_sessionmaker[AsyncSession]:
    """Return the global session factory, creating it if necessary."""
    global _session_factory
    if _session_factory is None:
        engine = create_engine(settings)
        _session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a database session.

    Rolls back on exception; always closes the session.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def dispose_engine() -> None:
    """Dispose the engine; used on application shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
