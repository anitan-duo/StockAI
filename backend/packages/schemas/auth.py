from uuid import UUID

from pydantic import ConfigDict, EmailStr, Field

from packages.schemas.base import BaseSchema


class Token(BaseSchema):
    """Token response schema."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseSchema):
    """JWT token payload schema."""

    sub: UUID
    email: EmailStr | None = None
    is_superuser: bool = False
    exp: int
    iat: int
    type: str = "access"
    jti: str | None = None

    model_config = ConfigDict(extra="allow")


class LoginRequest(BaseSchema):
    """Login request schema."""

    email: EmailStr
    password: str = Field(..., min_length=1)
    remember_me: bool = False


class RegisterRequest(BaseSchema):
    """Registration request schema."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


class RefreshRequest(BaseSchema):
    """Token refresh request schema."""

    refresh_token: str


class PasswordResetRequest(BaseSchema):
    """Password reset request schema."""

    email: EmailStr


class PasswordResetConfirm(BaseSchema):
    """Password reset confirmation schema."""

    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class AuthResponse(BaseSchema):
    """Auth response with user and tokens."""

    user: "UserResponse"
    tokens: Token

    model_config = ConfigDict(from_attributes=True)


# Import at the end to avoid circular imports
from packages.schemas.user import UserResponse
