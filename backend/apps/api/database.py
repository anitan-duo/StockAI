import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from apps.api.config import settings
from apps.api.db_guard import validate_for_mode

# Validate DATABASE_URL against STOCKAI_TEST_MODE before engine creation.
# In production (no STOCKAI_TEST_MODE) this is a no-op passthrough.
validated_url = validate_for_mode()

# Record the exact URL the engine is bound to, for regression tests that
# verify engines are never silently rebound by later env mutations.
ENGINE_URL: str = validated_url or settings.database_url


def create_engine() -> AsyncEngine:
    """Create async database engine.

    Reads settings.database_url which is resolved from DATABASE_URL at
    import time — callers must set DATABASE_URL (and STOCKAI_TEST_MODE)
    BEFORE importing this module. Mutating the env afterwards does not
    rebind the already-created singleton.
    """
    # NullPool when debug or in the Postgres integration suite: pooled
    # asyncpg connections are bound to the event loop that created them,
    # so reusing them across per-test loops raises "attached to a
    # different loop". Fresh connections per checkout make the suite
    # loop-safe. Production (no STOCKAI_TEST_MODE) is unchanged.
    _null_pool = settings.debug or os.environ.get("STOCKAI_TEST_MODE") == "postgres"
    return create_async_engine(
        ENGINE_URL,
        echo=settings.debug,
        poolclass=NullPool if _null_pool else None,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


engine = create_engine()

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database session. No auto-commit on reads."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database connection."""
    # Test connection
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: None)


async def close_db() -> None:
    """Close database connection."""
    await engine.dispose()
