from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import settings
from apps.api.database import get_session
from packages.schemas.auth import (
    Token,
    LoginRequest,
    RegisterRequest,
    RefreshRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    AuthResponse,
)
from apps.api.services.auth import auth_service

router = APIRouter(prefix="/auth", tags=["authentication"])

security = HTTPBearer(auto_error=False)


# Generic responses (anti-enumeration): auth failures must not reveal whether
# an email exists, whether it is a bad credential vs an inactive account, or
# whether the server-side lookup itself failed.
_GENERIC_LOGIN_DETAIL = "Invalid credentials"
_GENERIC_REGISTER_DETAIL = "Registration could not be completed"


async def _check_throttle(
    request: Request, endpoint: str, email: str, max_attempts: int | None = None
) -> None:
    """Valkey-backed fixed-window throttle, fail-open if Valkey is down.

    Counts attempts per IP+email in a window so a single endpoint cannot be
    brute-forced or used to spam registrations. Fail-open preserves
    availability when Valkey is unavailable; the login path is additionally
    protected by bcrypt cost and lockout-by-throttle once Valkey recovers.
    """
    ip = request.client.host if request.client else None
    limit = max_attempts if max_attempts is not None else settings.auth_login_max_attempts
    window = settings.auth_throttle_window_seconds
    try:
        from services.cache import get_valkey

        client = await get_valkey()
        if client is None:
            return
        key = f"{endpoint}_throttle:{ip}:{email.lower()}"
        attempts = await client.incr(key)
        if attempts == 1:
            await client.expire(key, window)
        if attempts > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts, try again later",
            )
    except HTTPException:
        raise
    except Exception:
        pass


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    session: AsyncSession = Depends(get_session),
):
    """Get current user from token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await auth_service.get_current_user(credentials.credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> AuthResponse:
    """Register a new user (throttled; generic response to avoid enumeration).

    Same per-IP+email throttle as login (configurable via
    AUTH_REGISTER_MAX_ATTEMPTS / AUTH_THROTTLE_WINDOW_SECONDS).
    Duplicate-email and any other registration failure are reported
    generically so registration cannot be used as an account-existence
    oracle.
    """
    await _check_throttle(
        request, "register", data.email, max_attempts=settings.auth_register_max_attempts
    )
    try:
        user = await auth_service.register(data)
        tokens = await auth_service.login(data.email, data.password)
        return AuthResponse(user=user, tokens=tokens)
    except ValueError:
        raise HTTPException(status_code=400, detail=_GENERIC_REGISTER_DETAIL)


@router.post("/login", response_model=Token)
async def login(
    data: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Token:
    """Login user (Valkey-backed brute-force throttle, fail-open).

    Auth failures are generic ("Invalid credentials") so login cannot be
    used to distinguish unknown emails, inactive accounts, or bad passwords.
    """
    await _check_throttle(request, "login", data.email)
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        tokens = await auth_service.login(
            data.email,
            data.password,
            data.remember_me,
            ip_address=ip,
            user_agent=user_agent,
        )
        return tokens
    except ValueError:
        raise HTTPException(status_code=401, detail=_GENERIC_LOGIN_DETAIL)


@router.post("/logout")
async def logout(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Logout user."""
    access_token = credentials.credentials if credentials else None
    refresh_token = request.headers.get("x-refresh-token")

    if access_token:
        await auth_service.logout(access_token, refresh_token)

    return {"message": "Logged out successfully"}


@router.post("/refresh", response_model=Token)
async def refresh(
    data: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> Token:
    """Refresh access token."""
    tokens = await auth_service.refresh_access_token(data.refresh_token)
    if not tokens:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    return tokens


@router.post("/forgot-password")
async def forgot_password(
    data: PasswordResetRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Request password reset (anti-enumeration: always generic; email sending not configured)."""
    # Email delivery is not configured in this deployment; do not enumerate accounts.
    return {"message": "If the email exists, a password reset link has been sent"}


@router.post("/reset-password")
async def reset_password(
    data: PasswordResetConfirm,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Reset password with token (not implemented: no email/token flow configured)."""
    raise HTTPException(status_code=501, detail="Password reset is not configured in this deployment")


@router.get("/me")
async def get_me(
    user = Depends(get_current_user),
) -> dict:
    """Get current user info."""
    # Return dict representation to avoid validation error on ORM object
    if hasattr(user, "id"):
        return {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
    return user  # type: ignore