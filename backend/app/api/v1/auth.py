"""Authentication API endpoints."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.config.settings import get_settings
from app.core.errors import AuthError, ErrorCode
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_csrf_token,
    verify_password,
)
from app.db.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserOut,
)
from app.services.audit.logger import AuditLogger

_log = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse, summary="Obtain access and refresh tokens")
async def login(
    body: LoginRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """
    Authenticate with username and password.

    Returns access + refresh tokens and sets a CSRF cookie.
    """
    result = await db.execute(
        select(User).where(User.username == body.username, User.deleted_at.is_(None))
    )
    user: User | None = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        _log.warning("login_failed", username=body.username)
        raise AuthError(ErrorCode.AUTH_INVALID_CREDENTIALS, "Invalid username or password")

    if not user.is_active:
        raise AuthError(ErrorCode.AUTH_USER_INACTIVE, "Account is deactivated")

    await db.refresh(user, ["role"])
    access = create_access_token(subject=user.id, role=user.role.name)
    refresh = create_refresh_token(subject=user.id)

    settings = get_settings()
    csrf_token = generate_csrf_token()
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        httponly=False,   # Must be readable by JS to set header
        samesite="strict",
        secure=settings.environment.value == "production",
        max_age=settings.csrf_token_expire_minutes * 60,
    )

    audit = AuditLogger(db)
    await audit.log(
        event_type="auth.login",
        actor_id=user.id,
        actor_username=user.username,
        entity_type="User",
        entity_id=user.id,
    )
    await db.commit()

    _log.info("login_success", username=user.username, role=user.role.name)
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
async def refresh_token(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Exchange a valid refresh token for a new access token."""
    from jose import JWTError

    try:
        payload = decode_token(body.refresh_token)
    except JWTError as exc:
        raise AuthError(ErrorCode.AUTH_TOKEN_INVALID, "Refresh token invalid") from exc

    if payload.get("type") != "refresh":
        raise AuthError(ErrorCode.AUTH_TOKEN_INVALID, "Not a refresh token")

    user = await db.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise AuthError(ErrorCode.AUTH_TOKEN_INVALID, "User not found")

    await db.refresh(user, ["role"])
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(subject=user.id, role=user.role.name),
        refresh_token=body.refresh_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserOut, summary="Current user profile")
async def get_me(current_user: CurrentUser) -> UserOut:
    """Return the authenticated user's profile."""
    return UserOut(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role.name,
        is_active=current_user.is_active,
    )


@router.post("/change-password", status_code=204, summary="Change own password")
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Change the authenticated user's password."""
    from app.core.security import hash_password

    if not verify_password(body.current_password, current_user.password_hash):
        raise AuthError(ErrorCode.AUTH_INVALID_CREDENTIALS, "Current password is incorrect")

    current_user.password_hash = hash_password(body.new_password)
    audit = AuditLogger(db)
    await audit.log(
        event_type="auth.password_changed",
        actor_id=current_user.id,
        actor_username=current_user.username,
        entity_type="User",
        entity_id=current_user.id,
    )
    await db.commit()
