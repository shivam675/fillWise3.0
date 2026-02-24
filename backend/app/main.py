"""
FillWise 3.0 — FastAPI application factory.

Application lifecycle:
  startup  → configure logging, run DB migrations, seed roles/admin
  shutdown → dispose DB engine pool
"""

from __future__ import annotations

import logging

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.v1.router import router as v1_router
from app.config.logging_config import configure_logging
from app.config.settings import get_settings
from app.core.errors import AppError
from app.core.middleware import (
    CorrelationIDMiddleware,
    SecurityHeadersMiddleware,
    app_error_handler,
    unhandled_exception_handler,
)

_log = structlog.get_logger(__name__)


def _create_limiter() -> Limiter:
    settings = get_settings()
    return Limiter(
        key_func=get_remote_address,
        default_limits=[settings.rate_limit_default],
    )


async def _startup(app: FastAPI) -> None:
    settings = get_settings()
    configure_logging(log_level=settings.log_level.value, json_logs=settings.log_json)
    _log.info(
        "fillwise_starting",
        version=settings.app_version,
        environment=settings.environment.value,
    )

    from alembic.config import Config
    from alembic import command

    # Run migrations synchronously (alembic/env.py now uses a sync engine)
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        _log.info("migrations_applied")
    except Exception as exc:
        logging.getLogger(__name__).warning("migration_warning: %s", exc)

    # Seed roles and admin
    await _seed_database()
    _log.info("fillwise_ready", host=settings.host, port=settings.port)


async def _seed_database() -> None:
    """Ensure roles exist and the bootstrap admin account is created if absent."""
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.models.user import Role, RoleEnum, User
    from app.db.session import get_session_factory

    settings = get_settings()
    factory = get_session_factory()

    async with factory() as db:
        # Upsert roles
        for role_enum in RoleEnum:
            result = await db.execute(select(Role).where(Role.name == role_enum.value))
            if result.scalar_one_or_none() is None:
                db.add(Role(name=role_enum.value, description=f"{role_enum.value} role"))

        await db.flush()

        # Bootstrap admin
        admin_result = await db.execute(
            select(User).where(User.username == settings.admin_username)
        )
        if admin_result.scalar_one_or_none() is None:
            admin_role = await db.execute(select(Role).where(Role.name == RoleEnum.ADMIN.value))
            role = admin_role.scalar_one()
            db.add(
                User(
                    username=settings.admin_username,
                    password_hash=hash_password(settings.admin_password.get_secret_value()),
                    role_id=role.id,
                    is_active=True,
                )
            )
            _log.info("admin_bootstrapped", username=settings.admin_username)

        await db.commit()


async def _shutdown() -> None:
    from app.db.session import dispose_engine
    await dispose_engine()
    _log.info("fillwise_shutdown")


def create_app() -> FastAPI:
    """Application factory. Returns a configured FastAPI instance."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "FillWise 3.0 — Local-First Legal Document Transformation Platform. "
            "All processing occurs on this machine; no data leaves the system."
        ),
        docs_url="/docs" if settings.environment.value != "production" else None,
        redoc_url="/redoc" if settings.environment.value != "production" else None,
        openapi_url="/openapi.json" if settings.environment.value != "production" else None,
    )

    # ── Startup / Shutdown ────────────────────────────────────────────── #
    @app.on_event("startup")
    async def on_startup() -> None:
        await _startup(app)

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        await _shutdown()

    # ── Rate Limiting ─────────────────────────────────────────────────── #
    limiter = _create_limiter()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── CORS ──────────────────────────────────────────────────────────── #
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
    )

    # ── Custom Middleware (applied in reverse order) ───────────────────── #
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    # ── Exception Handlers ────────────────────────────────────────────── #
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # ── Routes ────────────────────────────────────────────────────────── #
    app.include_router(v1_router)

    # ── Health ────────────────────────────────────────────────────────── #
    @app.get("/health", tags=["health"], summary="Health check")
    async def health() -> dict[str, object]:
        """Returns service health including DB and Ollama reachability."""
        import sqlalchemy as sa

        from app.db.session import get_session_factory
        from app.services.llm.client import OllamaClient

        db_ok = False
        try:
            factory = get_session_factory()
            async with factory() as db:
                await db.execute(sa.text("SELECT 1"))
            db_ok = True
        except Exception:
            pass

        ollama_ok = await OllamaClient().health_check()

        return {
            "status": "healthy" if (db_ok and ollama_ok) else "degraded",
            "database": "ok" if db_ok else "unavailable",
            "ollama": "ok" if ollama_ok else "unavailable",
            "version": settings.app_version,
        }

    # ── Metrics (Prometheus) ──────────────────────────────────────────── #
    @app.get("/metrics", tags=["observability"], summary="Prometheus metrics")
    async def metrics() -> object:
        from fastapi.responses import Response
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


# Entry point for uvicorn
app = create_app()
