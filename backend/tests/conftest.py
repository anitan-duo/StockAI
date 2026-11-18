"""Root test conftest — deterministic DB configuration BEFORE any app import.

This file runs before pytest collects any test module. It establishes:

- STOCKAI_TEST_MODE=sqlite (unless already set by orchestrator)
- DATABASE_URL=file-backed SQLite under /tmp (unique per process)
- REDIS_URL fallback (no live Valkey required for unit tests)
- Eviction of any stale apps.api.* modules imported by a previous
  collection phase in the same process (defensive; separate-process
  orchestrator is the primary isolation mechanism)

Integration tests under tests/integration/ set STOCKAI_TEST_MODE=postgres
via tests/integration/conftest.py and must run in a SEPARATE pytest
process — they are excluded from the SQLite run by the orchestrator
(tests/run_tests.py). Running pytest at the repo root without the
orchestrator will execute SQLite mode; integration tests will then fail
loudly via db_guard instead of silently using SQLite (see
tests/test_db_isolation.py).
"""
from __future__ import annotations

import os
import pathlib
import sys

# Deterministic SQLite config — must precede any apps.api.* import.
# Use STOCKAI_TEST_MODE to distinguish from the Postgres suite; do not
# rely on DATABASE_URL alone (see apps/api/db_guard.py).
os.environ.setdefault("STOCKAI_TEST_MODE", "sqlite")

# File-backed SQLite (not :memory: — async connections race on :memory:).
_TEST_DB = os.environ.get("STOCKAI_TEST_DB_PATH", "/tmp/stockai_test.db")
# If the orchestrator set a per-process path, honour it; else default.
# Validate via db_guard semantics inline (avoid importing app code here).
_expected_sqlite = f"sqlite+aiosqlite:///{_TEST_DB}"
_current = os.environ.get("DATABASE_URL", "")
if os.environ.get("STOCKAI_TEST_MODE") == "sqlite":
    if _current and not _current.startswith(("sqlite+aiosqlite:///", "sqlite:///")):
        raise RuntimeError(
            f"[sqlite suite] DATABASE_URL must be SQLite, got {_current!r}. "
            f"Unit tests must not connect to Postgres. "
            f"Unset DATABASE_URL or set it to sqlite+aiosqlite:////tmp/stockai_test.db."
        )
    os.environ["DATABASE_URL"] = _expected_sqlite if not _current else _current
    if ":memory:" in os.environ["DATABASE_URL"]:
        raise RuntimeError(
            "[sqlite suite] DATABASE_URL must be file-backed, not :memory:. "
            "Use sqlite+aiosqlite:////tmp/stockai_test.db."
        )
    # Clean slate so drop_all/create_all in fixtures is deterministic.
    try:
        if pathlib.Path(_TEST_DB).exists():
            pathlib.Path(_TEST_DB).unlink()
    except Exception:
        pass

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("VALKEY_URL", "redis://localhost:6379/0")
# Test mode does not read .env (by design), so the production SECRET_KEY
# guard would reject the placeholder default. Supply a deterministic
# test-only secret BEFORE settings are imported.
os.environ.setdefault("SECRET_KEY", "stockai-test-secret-key-0123456789abcdef")

# Evict stale app modules if a previous phase imported them with a
# different DATABASE_URL (e.g. mixed-mode invocation without separate
# processes — now a hard error via db_guard, this is just belt-and-braces).
for mod in list(sys.modules.keys()):
    if mod == "apps.api.database" or mod == "apps.api.config" or mod == "apps.api.db_guard":
        sys.modules.pop(mod, None)

# --- Shared fixtures (SQLite mode) ---------------------------------------
# Imported lazily inside fixtures so the env above is already set when
# apps.api.database is first imported.
from collections.abc import AsyncIterator  # noqa: E402

import pytest_asyncio  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _create_tables() -> AsyncIterator[None]:
    """Recreate schema per test on the SQLite file DB (dropping prior data).

    No-op in postgres mode (integration suite uses seeded real data —
    tests/integration/conftest.py takes precedence).
    """
    if os.environ.get("STOCKAI_TEST_MODE") != "sqlite":
        yield
        return
    from apps.api.models.base import Base

    import apps.api.models  # noqa: F401
    from apps.api.database import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
