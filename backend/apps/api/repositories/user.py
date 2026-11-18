from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.user import RefreshToken, Session, User
from apps.api.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """User repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> User | None:
        """Get user by email."""
        return await self.get_by_field("email", email.lower())

    async def get_active_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        """Get active users."""
        return await self.list(skip=skip, limit=limit, filters={"is_active": True})

    async def create_user(
        self,
        email: str,
        hashed_password: str,
        full_name: str | None = None,
        is_superuser: bool = False,
    ) -> User:
        """Create a new user."""
        return await self.create(
            email=email.lower(),
            hashed_password=hashed_password,
            full_name=full_name,
            is_superuser=is_superuser,
        )


class SessionRepository(BaseRepository[Session]):
    """Session repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(Session, session)

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        """Get session by token hash."""
        return await self.get_by_field("token_hash", token_hash)

    async def get_user_sessions(
        self, user_id: UUID, active_only: bool = True
    ) -> list[Session]:
        """Get all sessions for a user."""
        filters = {"user_id": user_id}
        if active_only:
            filters["is_revoked"] = False
        return await self.list(filters=filters, order_by="created_at")

    async def revoke_session(self, session_id: UUID) -> bool:
        """Revoke a session by ID."""
        session = await self.get(session_id)
        if session:
            session.is_revoked = True
            await self.session.flush()
            return True
        return False

    async def revoke_by_token_hash(self, token_hash: str) -> bool:
        """Revoke a session by token hash."""
        session = await self.get_by_token_hash(token_hash)
        if session:
            session.is_revoked = True
            await self.session.flush()
            return True
        return False

    async def revoke_user_sessions(self, user_id: UUID) -> int:
        """Revoke all sessions for a user."""
        from sqlalchemy import update

        result = await self.session.execute(
            update(Session)
            .where(Session.user_id == user_id)
            .values(is_revoked=True)
        )
        return result.rowcount

    async def cleanup_expired(self) -> int:
        """Clean up expired sessions."""
        from sqlalchemy import delete

        result = await self.session.execute(
            delete(Session).where(Session.expires_at < datetime.now(UTC))
        )
        return result.rowcount


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    """Refresh token repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(RefreshToken, session)

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        """Get refresh token by token hash."""
        return await self.get_by_field("token_hash", token_hash)

    async def get_user_tokens(self, user_id: UUID, valid_only: bool = True) -> list[RefreshToken]:
        """Get all refresh tokens for a user."""
        filters = {"user_id": user_id}
        tokens = await self.list(filters=filters, order_by="created_at")
        if valid_only:
            now = datetime.now(UTC)
            return [t for t in tokens if t.is_valid()]
        return tokens

    async def revoke_token(self, token_id: UUID) -> bool:
        """Revoke a refresh token by ID."""
        token = await self.get(token_id)
        if token:
            token.revoked_at = datetime.now(UTC)
            await self.session.flush()
            return True
        return False

    async def revoke_by_token_hash(self, token_hash: str) -> bool:
        """Revoke a refresh token by hash."""
        token = await self.get_by_token_hash(token_hash)
        if token:
            token.revoked_at = datetime.now(UTC)
            await self.session.flush()
            return True
        return False

    async def revoke_user_tokens(self, user_id: UUID) -> int:
        """Revoke all refresh tokens for a user."""
        from sqlalchemy import update

        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        return result.rowcount

    async def rotate_token(
        self, old_token_hash: str, new_token_hash: str, expires_at: datetime
    ) -> RefreshToken | None:
        """Rotate a refresh token (revoke old, create new)."""
        old_token = await self.get_by_token_hash(old_token_hash)
        if not old_token:
            return None

        old_token.revoked_at = datetime.now(UTC)
        old_token.replaced_by_token_hash = new_token_hash

        new_token = await self.create(
            user_id=old_token.user_id,
            token_hash=new_token_hash,
            expires_at=expires_at,
        )

        return new_token
