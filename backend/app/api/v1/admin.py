"""Admin user management endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, CurrentUser, get_db
from app.core.errors import ConflictError, ErrorCode, NotFoundError, ValidationError
from app.core.security import hash_password
from app.db.models.user import Role, User
from app.schemas.auth import CreateUserRequest, UserOut
from app.services.audit.logger import AuditLogger

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/users",
    response_model=list[UserOut],
    summary="List all users",
    dependencies=[AdminUser],
)
async def list_users(db: Annotated[AsyncSession, Depends(get_db)]) -> list[UserOut]:
    result = await db.execute(
        select(User).where(User.deleted_at.is_(None)).order_by(User.created_at)
    )
    users = result.scalars().all()
    out = []
    for u in users:
        await db.refresh(u, ["role"])
        out.append(
            UserOut(
                id=u.id,
                username=u.username,
                email=u.email,
                role=u.role.name,
                is_active=u.is_active,
            )
        )
    return out


@router.post(
    "/users",
    response_model=UserOut,
    status_code=201,
    summary="Create a new user",
    dependencies=[AdminUser],
)
async def create_user(
    body: CreateUserRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserOut:
    # Check username taken
    existing = await db.execute(
        select(User).where(User.username == body.username, User.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        raise ConflictError(ErrorCode.VALIDATION_ERROR, f"Username '{body.username}' is taken.")

    # Resolve role
    role_result = await db.execute(select(Role).where(Role.name == body.role))
    role = role_result.scalar_one_or_none()
    if role is None:
        raise ValidationError(
            f"Role '{body.role}' does not exist.",
            detail={"valid_roles": ["admin", "editor", "reviewer", "viewer"]},
        )

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role_id=role.id,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    audit = AuditLogger(db)
    await audit.log(
        event_type="user.created",
        actor_id=current_user.id,
        actor_username=current_user.username,
        entity_type="User",
        entity_id=user.id,
        payload={"username": user.username, "role": body.role},
    )
    await db.commit()
    await db.refresh(user, ["role"])

    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role.name,
        is_active=user.is_active,
    )


@router.delete(
    "/users/{user_id}",
    status_code=204,
    summary="Deactivate a user",
    dependencies=[AdminUser],
)
async def deactivate_user(
    user_id: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    user = await db.get(User, user_id)
    if user is None or user.is_deleted:
        raise NotFoundError("User", user_id)
    if user.id == current_user.id:
        raise ValidationError("You cannot deactivate your own account.")

    user.soft_delete()
    user.is_active = False
    audit = AuditLogger(db)
    await audit.log(
        event_type="user.deactivated",
        actor_id=current_user.id,
        actor_username=current_user.username,
        entity_type="User",
        entity_id=user.id,
    )
    await db.commit()
