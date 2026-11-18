from datetime import datetime
from uuid import UUID

from pydantic import ConfigDict, EmailStr, Field

from packages.schemas.base import BaseSchema


class UserPreferences(BaseSchema):
    """User preferences schema."""

    theme: str = Field(default="system", pattern="^(light|dark|system)$")
    default_market: str = Field(default="us")
    default_horizon: str = Field(default="1d", pattern="^(1d|1w|1m)$")
    notifications: dict = Field(default_factory=dict)


class UserBase(BaseSchema):
    """Base user schema."""

    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    preferences: UserPreferences = Field(default_factory=UserPreferences)


class UserCreate(UserBase):
    """User creation schema."""

    password: str = Field(..., min_length=8, max_length=128)


class UserUpdate(BaseSchema):
    """User update schema."""

    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    preferences: UserPreferences | None = None


class UserResponse(UserBase):
    """User response schema."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    last_login: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SessionResponse(BaseSchema):
    """Session response schema."""

    id: UUID
    created_at: datetime
    updated_at: datetime
    user_id: UUID
    expires_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None
    is_revoked: bool = False
    is_valid: bool = True

    model_config = ConfigDict(from_attributes=True)
