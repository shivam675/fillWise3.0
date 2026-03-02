"""
Security utilities: password hashing, JWT creation and verification.

Secrets are never logged. All operations are timing-safe.
"""

from __future__ import annotations

import secrets
import hashlib
from datetime import UTC, datetime, timedelta

import bcrypt
from jose import jwt

from app.config.settings import get_settings


# ── Password ──────────────────────────────────────────────────────────── #


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    normalized = hashlib.sha256(plain.encode("utf-8")).hexdigest().encode("utf-8")
    return bcrypt.hashpw(normalized, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify a plaintext password against a stored hash.

    Returns False (never raises) on any error; prevents timing oracles.
    """
    try:
        normalized = hashlib.sha256(plain.encode("utf-8")).hexdigest().encode("utf-8")
        return bcrypt.checkpw(normalized, hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT ───────────────────────────────────────────────────────────────── #


def _now_utc() -> datetime:
    return datetime.now(UTC)


def create_access_token(
    subject: str,
    role: str,
    extra_claims: dict[str, object] | None = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject: The user ID (``sub`` claim).
        role: The user role name.
        extra_claims: Optional additional claims merged into the payload.

    Returns:
        Signed compact JWT string.
    """
    settings = get_settings()
    expire = _now_utc() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload: dict[str, object] = {
        "sub": subject,
        "role": role,
        "iat": _now_utc(),
        "exp": expire,
        "type": "access",
        "jti": secrets.token_hex(16),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(subject: str) -> str:
    """Create a signed JWT refresh token (no role claim)."""
    settings = get_settings()
    expire = _now_utc() + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload: dict[str, object] = {
        "sub": subject,
        "iat": _now_utc(),
        "exp": expire,
        "type": "refresh",
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict[str, object]:
    """
    Decode and validate a JWT.

    Raises:
        JWTError: If the token is invalid, expired, or tampered with.
    """
    settings = get_settings()
    return jwt.decode(  # type: ignore[return-value]
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_urlsafe(32)


def safe_str_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return secrets.compare_digest(a.encode(), b.encode())


# ── WebSocket Tickets ─────────────────────────────────────────────────── #


def create_ws_ticket(user_id: str, role: str) -> str:
    """
    Create a short-lived JWT ticket for WebSocket authentication.

    Unlike access tokens, tickets are single-use and very short TTL,
    preventing exposure in server logs or browser history.
    """
    settings = get_settings()
    expire = _now_utc() + timedelta(seconds=settings.ws_ticket_expire_seconds)
    payload: dict[str, object] = {
        "sub": user_id,
        "role": role,
        "iat": _now_utc(),
        "exp": expire,
        "type": "ws_ticket",
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def verify_ws_ticket(ticket: str) -> dict[str, object]:
    """
    Decode and validate a WebSocket ticket.

    Raises JWTError if invalid, expired, or not a ws_ticket type.
    """
    settings = get_settings()
    payload = jwt.decode(
        ticket,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != "ws_ticket":
        from jose import JWTError
        raise JWTError("Not a WebSocket ticket")
    return payload  # type: ignore[return-value]


# ── Re-export for downstream ──────────────────────────────────────────── #

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "create_ws_ticket",
    "decode_token",
    "generate_csrf_token",
    "hash_password",
    "safe_str_compare",
    "verify_password",
    "verify_ws_ticket",
]
