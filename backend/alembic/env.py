"""Alembic environment configuration for async SQLAlchemy."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config.settings import get_settings
from app.db.base import Base

# Import all models so their tables are visible to Alembic
import app.db.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    # Allow override via -x db_url=... on the CLI
    url = context.get_x_argument(as_dictionary=True).get("db_url")
    if url:
        return url
    return str(get_settings().database_url)


def get_sync_url() -> str:
    """Convert async driver URLs to sync equivalents for Alembic."""
    url = get_url()
    # aiosqlite → plain sqlite
    url = url.replace("+aiosqlite", "")
    # asyncpg → psycopg2 (Postgres)
    url = url.replace("+asyncpg", "")
    return url


def run_migrations_offline() -> None:
    url = get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations using a synchronous engine (safe from any context)."""
    engine = create_engine(get_sync_url())
    with engine.connect() as connection:
        do_run_migrations(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
