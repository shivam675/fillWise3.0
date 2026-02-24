"""
Application configuration via Pydantic Settings.

All values are sourced from environment variables or an .env file.
No defaults expose insecure behaviour in production.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import (
    AnyHttpUrl,
    BeforeValidator,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment identifiers."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Structured log level options."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def _parse_cors_origins(value: str | list[str]) -> list[str]:
    """Accept comma-separated string or list for CORS origins."""
    if isinstance(value, list):
        return value
    return [origin.strip() for origin in value.split(",") if origin.strip()]


class Settings(BaseSettings):
    """
    Centralised, type-validated application configuration.

    Reads from environment variables with an optional .env file.
    All secrets are Pydantic SecretStr to prevent accidental logging.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
    )

    # ── Application ────────────────────────────────────────────────────── #
    app_name: str = Field(default="FillWise", description="Human-readable application name")
    app_version: str = Field(default="3.0.0", description="Semantic version string")
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Deployment environment (development|testing|production)",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode. Must be False in production.",
    )

    # ── Server ─────────────────────────────────────────────────────────── #
    host: str = Field(default="127.0.0.1", description="Bind host. Default local-only.")
    port: int = Field(default=8000, ge=1024, le=65535, description="Bind port")
    workers: int = Field(default=1, ge=1, le=16, description="Uvicorn worker processes")
    reload: bool = Field(default=False, description="Auto-reload on code change (dev only)")

    # ── CORS ───────────────────────────────────────────────────────────── #
    cors_origins: Annotated[list[str], BeforeValidator(_parse_cors_origins)] = Field(
        default=["http://localhost:5173"],
        description="Comma-separated list of allowed CORS origins",
    )

    # ── Database ───────────────────────────────────────────────────────── #
    database_url: str = Field(
        default="sqlite+aiosqlite:///./fillwise.db",
        description=(
            "Async SQLAlchemy connection string. "
            "Use sqlite+aiosqlite:// for local or postgresql+asyncpg:// for production."
        ),
    )
    db_pool_size: int = Field(default=5, ge=1, le=50, description="Connection pool size")
    db_max_overflow: int = Field(default=10, ge=0, le=100, description="Pool max overflow")
    db_echo: bool = Field(default=False, description="Log all SQL statements (debug only)")

    # ── Auth / JWT ─────────────────────────────────────────────────────── #
    jwt_secret_key: SecretStr = Field(
        ...,
        description="HS256 signing secret. Minimum 32 characters. Required.",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_access_token_expire_minutes: int = Field(
        default=60,
        ge=5,
        le=1440,
        description="Access token TTL in minutes",
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Refresh token TTL in days",
    )

    # ── Ollama ─────────────────────────────────────────────────────────── #
    ollama_base_url: AnyHttpUrl = Field(
        default="http://127.0.0.1:11434",
        description="Ollama API base URL. Must resolve locally.",
    )
    ollama_model: str = Field(
        default="ministral:3b",
        description="Ollama model name to use for rewrites",
    )
    ollama_timeout_seconds: int = Field(
        default=120,
        ge=10,
        le=600,
        description="HTTP timeout for Ollama API calls (seconds)",
    )
    ollama_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts on transient Ollama failures",
    )
    ollama_circuit_breaker_threshold: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Consecutive failures before circuit opens",
    )
    ollama_circuit_breaker_timeout_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
        description="Seconds to wait before testing circuit again",
    )

    # ── File Storage ───────────────────────────────────────────────────── #
    upload_dir: Path = Field(
        default=Path("./uploads"),
        description="Directory for uploaded source documents",
    )
    export_dir: Path = Field(
        default=Path("./exports"),
        description="Directory for assembled output documents",
    )
    rules_dir: Path = Field(
        default=Path("./rules"),
        description="Directory for YAML rule files",
    )
    max_upload_size_mb: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Maximum upload file size in MB",
    )
    allowed_mime_types: list[str] = Field(
        default=[
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
        description="Allowed MIME types for uploaded documents",
    )

    # ── Rate Limiting ──────────────────────────────────────────────────── #
    rate_limit_default: str = Field(
        default="100/minute",
        description="Default rate limit string (slowapi format)",
    )
    rate_limit_upload: str = Field(
        default="10/minute",
        description="Rate limit for upload endpoints",
    )
    rate_limit_auth: str = Field(
        default="20/minute",
        description="Rate limit for auth endpoints",
    )

    # ── Logging ────────────────────────────────────────────────────────── #
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Minimum log level")
    log_json: bool = Field(default=True, description="Emit logs as JSON (False for dev console)")
    log_file: Path | None = Field(default=None, description="Optional log file path")

    # ── Processing ─────────────────────────────────────────────────────── #
    max_document_pages: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum pages allowed per document",
    )
    chunk_max_tokens: int = Field(
        default=1500,
        ge=100,
        le=4000,
        description="Maximum tokens per section chunk sent to LLM",
    )
    rewrite_temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="Ollama sampling temperature for rewrites (lower = more deterministic)",
    )

    # ── CSRF ───────────────────────────────────────────────────────────── #
    csrf_cookie_name: str = Field(default="fillwise_csrf", description="CSRF cookie name")
    csrf_header_name: str = Field(default="X-CSRF-Token", description="CSRF header name")
    csrf_token_expire_minutes: int = Field(
        default=60,
        ge=5,
        le=1440,
        description="CSRF token TTL in minutes",
    )

    # ── Admin Bootstrap ────────────────────────────────────────────────── #
    admin_username: str = Field(
        default="admin",
        description="Bootstrap admin username (used only on first startup)",
    )
    admin_password: SecretStr = Field(
        ...,
        description="Bootstrap admin password. Required. Min 12 chars.",
    )

    # ── Validators ─────────────────────────────────────────────────────── #

    @field_validator("jwt_secret_key")
    @classmethod
    def jwt_secret_must_be_strong(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 32:
            raise ValueError("jwt_secret_key must be at least 32 characters")
        return v

    @field_validator("admin_password")
    @classmethod
    def admin_password_must_be_strong(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 12:
            raise ValueError("admin_password must be at least 12 characters")
        return v

    @model_validator(mode="after")
    def production_safety_checks(self) -> Settings:
        if self.environment == Environment.PRODUCTION:
            if self.debug:
                raise ValueError("debug must be False in production")
            if self.reload:
                raise ValueError("reload must be False in production")
            if self.db_echo:
                raise ValueError("db_echo must be False in production")
        return self

    @model_validator(mode="after")
    def ensure_directories_exist(self) -> Settings:
        """Create storage directories if they do not exist."""
        for directory in (self.upload_dir, self.export_dir, self.rules_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the cached Settings singleton.

    Use dependency injection in FastAPI routes:
        settings: Settings = Depends(get_settings)
    """
    return Settings()
