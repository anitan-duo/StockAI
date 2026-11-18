import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from jose import jwt
from passlib.context import CryptContext

from apps.api.config import settings
from apps.api.database import async_session_factory
from apps.api.models.user import User, Session, RefreshToken
from apps.api.repositories.user import (
    UserRepository,
    SessionRepository,
    RefreshTokenRepository,
)
from packages.schemas.auth import Token, TokenPayload, LoginRequest, RegisterRequest


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Authentication service."""

    def __init__(self):
        pass

    async def _get_repos(self):
        async with async_session_factory() as session:
            return (
                UserRepository(session),
                SessionRepository(session),
                RefreshTokenRepository(session),
                session,
            )

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Hash a password."""
        return pwd_context.hash(password)

    def create_access_token(
        self, user: User, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a JWT access token."""
        import uuid

        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=settings.access_token_expire_minutes
            )

        payload = {
            "sub": str(user.id),
            "email": user.email,
            "is_superuser": user.is_superuser,
            "exp": int(expire.timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "type": "access",
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    def create_refresh_token(self, user: User, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT refresh token."""
        import uuid

        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                days=settings.refresh_token_expire_days
            )

        payload = {
            "sub": str(user.id),
            "exp": int(expire.timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
            "type": "refresh",
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    def decode_token(self, token: str) -> Optional[TokenPayload]:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(
                token, settings.secret_key, algorithms=[settings.jwt_algorithm]
            )
            return TokenPayload(**payload)
        except jwt.JWTError:
            return None

    async def authenticate(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user with email and password."""
        user_repo, _, _, _ = await self._get_repos()
        user = await user_repo.get_by_email(email)
        if not user or not user.is_active:
            return None
        if not self.verify_password(password, user.hashed_password):
            return None
        return user

    async def register(self, data: RegisterRequest) -> User:
        """Register a new user."""
        user_repo, _, _, session = await self._get_repos()

        # Check if user exists
        existing = await user_repo.get_by_email(data.email)
        if existing:
            raise ValueError("Email already registered")

        hashed_password = self.get_password_hash(data.password)
        user = await user_repo.create_user(
            email=data.email,
            hashed_password=hashed_password,
            full_name=data.full_name,
        )
        await session.commit()
        return user

    async def login(
        self,
        email: str,
        password: str,
        remember_me: bool = False,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Token:
        """Login user and create tokens."""
        user = await self.authenticate(email, password)
        if not user:
            raise ValueError("Invalid credentials")

        user_repo, session_repo, refresh_repo, session = await self._get_repos()

        # Create access token
        access_token = self.create_access_token(user)

        # Create refresh token
        refresh_expire = (
            timedelta(days=30) if remember_me
            else timedelta(days=settings.refresh_token_expire_days)
        )
        refresh_token = self.create_refresh_token(user, refresh_expire)

        # Store session
        session_expire = datetime.now(timezone.utc) + (
            timedelta(days=30) if remember_me
            else timedelta(minutes=settings.access_token_expire_minutes)
        )
        await session_repo.create(
            user_id=user.id,
            token_hash=self._hash_token(access_token),
            expires_at=session_expire,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Store refresh token
        refresh_expire_dt = datetime.now(timezone.utc) + refresh_expire
        await refresh_repo.create(
            user_id=user.id,
            token_hash=self._hash_token(refresh_token),
            expires_at=refresh_expire_dt,
        )

        # Update last login
        user.last_login = datetime.now(timezone.utc)
        await session.commit()

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=int(refresh_expire.total_seconds()),
        )

    async def logout(self, access_token: str, refresh_token: Optional[str] = None) -> bool:
        """Logout user by revoking tokens."""
        _, session_repo, refresh_repo, session = await self._get_repos()

        # Revoke session by hash
        await session_repo.revoke_by_token_hash(self._hash_token(access_token))

        # Revoke refresh token if provided
        if refresh_token:
            await refresh_repo.revoke_by_token_hash(self._hash_token(refresh_token))

        await session.commit()
        return True

    async def refresh_access_token(self, refresh_token: str) -> Optional[Token]:
        """Refresh access token using refresh token."""
        payload = self.decode_token(refresh_token)
        if not payload or payload.type != "refresh":
            return None

        user_repo, session_repo, refresh_repo, session = await self._get_repos()

        # Verify refresh token exists and is valid
        stored_token = await refresh_repo.get_by_token_hash(self._hash_token(refresh_token))
        if not stored_token or not stored_token.is_valid():
            return None

        # Get user
        user = await user_repo.get(payload.sub)
        if not user or not user.is_active:
            return None

        # Rotate refresh token
        new_refresh_token = self.create_refresh_token(user)
        new_refresh_expire = datetime.now(timezone.utc) + timedelta(
            days=settings.refresh_token_expire_days
        )

        await refresh_repo.rotate_token(
            self._hash_token(refresh_token),
            self._hash_token(new_refresh_token),
            new_refresh_expire,
        )

        # Create new access token
        new_access_token = self.create_access_token(user)

        # Create new session
        session_expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes
        )
        await session_repo.create(
            user_id=user.id,
            token_hash=self._hash_token(new_access_token),
            expires_at=session_expire,
        )

        await session.commit()

        return Token(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=settings.refresh_token_expire_days * 24 * 3600,
        )

    async def get_current_user(self, token: str) -> Optional[User]:
        """Get current user from access token with revocation check."""
        payload = self.decode_token(token)
        if not payload or payload.type != "access":
            return None

        user_repo, session_repo, _, _ = await self._get_repos()
        # Check session revocation — fail closed: a session that cannot be
        # verified must not authenticate (revocation window defence).
        try:
            session = await session_repo.get_by_token_hash(self._hash_token(token))
            if not session or session.is_revoked:
                return None
            # Check expiry with timezone robustness (SQLite naive vs aware)
            expires_at = session.expires_at
            if expires_at and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at and expires_at < datetime.now(timezone.utc):
                return None
        except Exception:
            logging.getLogger("stockai.api").exception("session revocation check failed")
            return None

        try:
            user = await user_repo.get(payload.sub)
        except Exception:
            logging.getLogger("stockai.api").exception("user lookup failed in get_current_user")
            return None
        if not user or not user.is_active:
            return None
        return user

    async def change_password(
        self, user_id: UUID, current_password: str, new_password: str
    ) -> bool:
        """Change user password."""
        user_repo, _, _, session = await self._get_repos()
        user = await user_repo.get(user_id)
        if not user:
            return False
        if not self.verify_password(current_password, user.hashed_password):
            return False
        user.hashed_password = self.get_password_hash(new_password)
        # Revoke all sessions and tokens
        await self._revoke_all_user_tokens(user_id)
        await session.commit()
        return True

    async def _revoke_all_user_tokens(self, user_id: UUID) -> None:
        """Revoke all tokens for a user."""
        _, session_repo, refresh_repo, session = await self._get_repos()
        await session_repo.revoke_user_sessions(user_id)
        await refresh_repo.revoke_user_tokens(user_id)
        await session.commit()

    def _hash_token(self, token: str) -> str:
        """Hash a token for storage."""
        import hashlib
        return hashlib.sha256(token.encode()).hexdigest()


# Global auth service instance
auth_service = AuthService()