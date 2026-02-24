"""Auth schemas: login, token response, user representations."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=12, max_length=256)

    @field_validator("new_password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserOut(BaseModel):
    id: str
    username: str
    email: str | None
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_\-]+$")
    email: str | None = Field(default=None, max_length=255)
    password: str = Field(..., min_length=12, max_length=256)
    role: str = Field(..., description="Role name: admin | editor | reviewer | viewer")
