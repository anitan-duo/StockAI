"""Integration-test conftest — PostgreSQL mode, isolated test database.

Runs in a SEPARATE pytest process from the SQLite suite (see
tests/run_tests.py). Establishes:

- STOCKAI_TEST_MODE=postgres
- DATABASE_URL=postgresql+asyncpg://.../stockai_test (validated by
  apps.api.db_guard — refuses the production `stockai` DB unless
  STOCKAI_ALLOW_PROD_DB=1 is explicitly set for legacy seeded-DB runs)
- Verifies Postgres is reachable before tests (clear failure message)

The alembic migrations are applied once per process to the *test* DB by
the orchestrator (tests/run_tests.py --prepare-postgres) or lazily here
on first import if needed. No silent SQLite fallback: if DATABASE_URL is
SQLite, db_guard raises before any engine is created.
"""
from __future__ import annotations

import os
import sys

# Must be set BEFORE any apps.api.* import.
os.environ["STOCKAI_TEST_MODE"] = "postgres"

_default_pg_url = "postgresql+asyncpg://stockai:stockai@localhost:5432/stockai_test"
_pg_url = os.environ.get("DATABASE_URL", _default_pg_url)
# If the orchestrator didn't set it, use the isolated test DB default.
# If it set a prod URL without STOCKAI_ALLOW_PROD_DB, db_guard will refuse.
if not _pg_url:
    _pg_url = _default_pg_url
os.environ["DATABASE_URL"] = _pg_url
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("VALKEY_URL", "redis://localhost:6379/0")
# Test mode does not read .env (by design); provide a deterministic
# test-only secret so the production guard does not reject collection.
os.environ.setdefault("SECRET_KEY", "stockai-test-secret-key-0123456789abcdef")

# Evict stale modules (defensive; separate process is primary isolation).
for mod in list(sys.modules.keys()):
    if mod in ("apps.api.database", "apps.api.config", "apps.api.db_guard"):
        sys.modules.pop(mod, None)

# --- Reachability check (fail fast with clear message) --------------------
def _check_postgres_reachable() -> None:
    import asyncio
    import socket

    url = os.environ.get("DATABASE_URL", "")
    # Parse host:port without importing app code.
    host, port = "localhost", 5432
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname or host
        port = parsed.port or port
    except Exception:
        pass
    try:
        with socket.create_connection((host, port), timeout=5):
            pass
    except OSError as exc:
        raise RuntimeError(
            f"[postgres suite] Cannot connect to PostgreSQL at {host}:{port} ({exc}). "
            f"Start it with: docker start stockai-postgres "
            f"(or: docker compose up -d postgres). "
            f"Integration tests require live Postgres; they will not fall back to SQLite."
        ) from exc


_check_postgres_reachable()

# --- No autouse drop_all here: integration tests use seeded real data ---
# The orchestrator seeds stockai_test from the dev `stockai` DB (or runs
# migrations + seed script). Dropping tables per-test would destroy the
# seed. Tests that need isolation create uniquely-named rows and roll back.
from collections.abc import AsyncIterator  # noqa: E402,F401

import pytest  # noqa: E402,F401
import pytest_asyncio  # noqa: E402
