"""Shared fixtures for ML tests.

In-memory SQLite stubs every DB-touching fixture so the calibrations,
feature-alignment, revenue pipeline and prediction tests can run in CI
without a Postgres server attached. Real integration tests still hit the
production URL; this only applies to ``tests/ml`` and unit-level service
tests that need persistence but should not require a live DB.
"""
from __future__ import annotations

import os
import sys
import pathlib

DB_PATH = os.environ.get("STOCKAI_TEST_DB_PATH", "/tmp/stockai_test.db")
if pathlib.Path(DB_PATH).exists():
    try:
        pathlib.Path(DB_PATH).unlink()
    except Exception:
        pass

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH}"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

# Clear cached modules if any imported with old settings
for mod in list(sys.modules.keys()):
    if "apps.api.database" in mod or "apps.api.config" in mod:
        sys.modules.pop(mod)

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest_asyncio.fixture(autouse=True)
async def _create_tables() -> AsyncIterator[None]:
    from apps.api.models.base import Base
    import apps.api.models  # noqa
    from apps.api.database import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Yield an AsyncSession backed by the SQLite test DB."""
    from apps.api.database import async_session_factory

    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def sync_db_session() -> AsyncIterator[Session]:
    """Yield a sync Session backed by the same SQLite test DB."""
    from apps.api.models.base import Base
    import apps.api.models  # noqa

    sync_engine = create_engine(f"sqlite:///{DB_PATH}")
    Base.metadata.create_all(sync_engine)
    with Session(sync_engine) as s:
        yield s
