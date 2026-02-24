"""
Database models for users and roles.

Roles table uses a fixed enum set enforced at the application layer;
stored as a string for schema portability across SQLite and PostgreSQL.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RoleEnum(StrEnum):
    """Application-level role definitions."""

    ADMIN = "admin"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Role entity. Seeded on first startup."""

    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")

    users: Mapped[list[User]] = relationship("User", back_populates="role")

    def __repr__(self) -> str:
        return f"<Role {self.name}>"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """User entity with hashed password and role reference."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("username", name="uq_users_username"),)

    username: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    role_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    role: Mapped[Role] = relationship("Role", back_populates="users")

    def __repr__(self) -> str:
        return f"<User {self.username}>"
