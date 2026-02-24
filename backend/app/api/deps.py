"""
FastAPI dependency providers.

All authentication and authorization logic lives here, not in routes.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthError, ErrorCode, ForbiddenError
from app.core.security import decode_token, safe_str_compare
from app.db.models.user import RoleEnum, User
from app.db.session import get_db

_log = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Validate JWT Bearer token and return the authenticated User.

    Raises AuthError on any JWT problem.
    """
    if credentials is None:
        raise AuthError(
            ErrorCode.AUTH_TOKEN_INVALID, "Authorization header missing or not Bearer type"
        )

    try:
        payload = decode_token(credentials.credentials)
    except JWTError as exc:
        raise AuthError(ErrorCode.AUTH_TOKEN_INVALID, "Token invalid or expired") from exc

    if payload.get("type") != "access":
        raise AuthError(ErrorCode.AUTH_TOKEN_INVALID, "Token is not an access token")

    user_id: str | None = payload.get("sub")  # type: ignore[assignment]
    if not user_id:
        raise AuthError(ErrorCode.AUTH_TOKEN_INVALID, "Token missing subject")

    user_result = await db.execute(
        select(User)
        .options(selectinload(User.role))
        .where(User.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None or user.is_deleted:
        raise AuthError(ErrorCode.AUTH_TOKEN_INVALID, "User not found")

    if not user.is_active:
        raise AuthError(ErrorCode.AUTH_USER_INACTIVE, "Account is deactivated")

    structlog.contextvars.bind_contextvars(
        user_id=user.id, username=user.username
    )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: RoleEnum):
    """Return a dependency callable that enforces role membership."""

    async def _check(user: CurrentUser) -> User:
        if user.role.name not in [r.value for r in roles]:
            raise ForbiddenError(
                f"This action requires one of: {[r.value for r in roles]}. "
                f"Your role is: {user.role.name}"
            )
        return user

    return _check


AdminUser = Depends(require_roles(RoleEnum.ADMIN))
EditorUser = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.EDITOR))
ReviewerUser = Depends(require_roles(RoleEnum.ADMIN, RoleEnum.EDITOR, RoleEnum.REVIEWER))


async def get_csrf_token(
    request: Request,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    """
    Validate CSRF double-submit cookie for state-mutating requests.

    GET / HEAD / OPTIONS are exempt.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    cookie_token = request.cookies.get("fillwise_csrf")
    if not cookie_token:
        from app.core.errors import AuthError, ErrorCode
        raise AuthError(ErrorCode.AUTH_CSRF_INVALID, "CSRF cookie missing")

    if not x_csrf_token:
        from app.core.errors import AuthError, ErrorCode
        raise AuthError(ErrorCode.AUTH_CSRF_INVALID, "X-CSRF-Token header missing")

    if not safe_str_compare(cookie_token, x_csrf_token):
        from app.core.errors import AuthError, ErrorCode
        raise AuthError(ErrorCode.AUTH_CSRF_INVALID, "CSRF token mismatch")
