"""Regression tests for DB isolation (Phase 2 §6).

These run in the SQLite suite (default). They verify:
1. SQLite config established before engine creation.
2. Postgres config established before engine creation.
3. Changing env vars after engine init cannot silently create a
   misleading result (engine is bound at import; env mutation is inert).
4. Unit tests cannot accidentally connect to Postgres.
5. Integration tests cannot silently fall back to SQLite.
6. Test DB safeguards reject unsafe DB targets.
7. Orchestrator detects failed/unavailable groups (tested via dry-run
   helpers, not by re-running the full suite).

No live Postgres is required for these tests — they inspect URLs,
import order, and guard functions only.
"""
from __future__ import annotations

import os
import subprocess
import sys


def test_sqlite_config_before_engine():
    """SQLite suite: DATABASE_URL is SQLite and ENGINE_URL matches it."""
    os.environ["STOCKAI_TEST_MODE"] = "sqlite"
    # Re-import in isolation — conftest already set SQLite before first
    # app import, so the live singleton must be SQLite.
    from apps.api import db_guard

    assert db_guard.is_sqlite_url(os.environ.get("DATABASE_URL", ""))
    # validate_for_mode must accept the current env without raising.
    validated = db_guard.validate_for_mode()
    assert db_guard.is_sqlite_url(validated)

    # The engine module must have recorded the same URL at import time.
    import apps.api.database as db_mod

    # ENGINE_URL is the bound URL; it must be SQLite in this suite.
    assert db_guard.is_sqlite_url(db_mod.ENGINE_URL)
    # And the live engine's URL must be SQLite too.
    live_url = str(db_mod.engine.url)
    assert db_guard.is_sqlite_url(live_url) or "sqlite" in live_url


def test_postgres_config_before_engine_guard():
    """Postgres config validation: *_test DB accepted, prod rejected."""
    from apps.api import db_guard

    # Valid isolated test DB.
    ok = "postgresql+asyncpg://stockai:stockai@localhost:5432/stockai_test"
    assert db_guard.ensure_test_postgres_url(ok) == ok
    assert db_guard.is_postgres_url(ok)
    assert db_guard.parse_postgres_db_name(ok) == "stockai_test"

    # Production DB must be rejected without explicit opt-in.
    prod = "postgresql+asyncpg://stockai:stockai@localhost:5432/stockai"
    try:
        db_guard.ensure_test_postgres_url(prod)
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "stockai" in str(exc)

    assert raised, "ensure_test_postgres_url must refuse the production 'stockai' DB"

    # Non-_test database must be rejected.
    dev = "postgresql+asyncpg://stockai:stockai@localhost:5432/mydevdb"
    try:
        db_guard.ensure_test_postgres_url(dev)
        raised = False
    except RuntimeError:
        raised = True

    assert raised, "ensure_test_postgres_url must require *_test suffix"


def test_env_change_after_engine_init_is_inert():
    """Mutating DATABASE_URL after import must NOT rebind the engine."""
    import apps.api.database as db_mod
    from apps.api import db_guard

    original_engine_url = str(db_mod.engine.url)
    original_engine_id = id(db_mod.engine)
    original_engine_url_recorded = db_mod.ENGINE_URL

    # Mutate env to a different (still SQLite) URL — must not affect engine.
    old_env = os.environ.get("DATABASE_URL")
    old_mode = os.environ.get("STOCKAI_TEST_MODE")
    try:
        os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/stockai_other.db"
        os.environ["STOCKAI_TEST_MODE"] = "sqlite"

        # Re-reading env does not change the already-bound engine.
        assert str(db_mod.engine.url) == original_engine_url
        assert id(db_mod.engine) == original_engine_id
        assert db_mod.ENGINE_URL == original_engine_url_recorded

        # If someone tries to assert the new env against the old engine,
        # the guard must detect the mismatch when it matters (different
        # dialect). SQLite->SQLite different path is allowed by
        # assert_engine_matches_url (only checks dialect), but a
        # SQLite->Postgres flip must raise.
        try:
            db_guard.assert_engine_matches_url(
                original_engine_url,
                "postgresql+asyncpg://stockai:stockai@localhost:5432/stockai_test",
            )
            raised = False
        except RuntimeError:
            raised = True

        assert raised, "assert_engine_matches_url must catch SQLite-vs-Postgres mismatch"
    finally:
        if old_env is not None:
            os.environ["DATABASE_URL"] = old_env
        else:
            os.environ.pop("DATABASE_URL", None)
        if old_mode is not None:
            os.environ["STOCKAI_TEST_MODE"] = old_mode
        else:
            os.environ.pop("STOCKAI_TEST_MODE", None)


def test_unit_tests_cannot_connect_to_postgres():
    """In sqlite mode, ensure_sqlite_url rejects Postgres URLs."""
    from apps.api import db_guard

    pg = "postgresql+asyncpg://stockai:stockai@localhost:5432/stockai"
    try:
        db_guard.ensure_sqlite_url(pg)
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "SQLite" in str(exc) or "sqlite" in str(exc).lower()

    assert raised, "Unit (sqlite) suite must refuse Postgres URLs"

    # :memory: must also be refused (async race).
    try:
        db_guard.ensure_sqlite_url("sqlite+aiosqlite:///:memory:")
        raised = False
    except RuntimeError:
        raised = True

    assert raised, "SQLite suite must refuse :memory: (file-backed required)"

    # Unset must be refused (no silent default to prod Postgres).
    try:
        db_guard.ensure_sqlite_url(None)
        raised = False
    except RuntimeError:
        raised = True

    assert raised, "SQLite suite must refuse missing DATABASE_URL"


def test_integration_tests_cannot_fall_back_to_sqlite():
    """In postgres mode, ensure_test_postgres_url rejects SQLite URLs."""
    from apps.api import db_guard

    sqlite = "sqlite+aiosqlite:////tmp/stockai_test.db"
    try:
        db_guard.ensure_test_postgres_url(sqlite)
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "PostgreSQL" in str(exc) or "postgres" in str(exc).lower()

    assert raised, "Integration must refuse SQLite URLs (no silent fallback)"

    try:
        db_guard.ensure_test_postgres_url(None)
        raised = False
    except RuntimeError:
        raised = True

    assert raised, "Integration must refuse missing DATABASE_URL"


def test_safeguards_reject_unsafe_targets():
    """Safeguard unit tests: redaction, parsing, mode detection."""
    from apps.api import db_guard

    # Password redaction — credentials must never appear in messages.
    redacted = db_guard._strip_password_from_message(
        "postgresql+asyncpg://stockai:supersecret@localhost:5432/stockai_test"
    )
    assert "supersecret" not in redacted
    assert "***" in redacted

    # DB name parsing.
    assert db_guard.parse_postgres_db_name("postgresql+asyncpg://u:p@h:5432/my_test?x=1") == "my_test"
    assert db_guard.parse_postgres_db_name("sqlite+aiosqlite:////tmp/x.db") is None

    # Mode detection: unknown mode is treated as production (no guard).
    old = os.environ.get("STOCKAI_TEST_MODE")
    try:
        os.environ["STOCKAI_TEST_MODE"] = "bogus"
        assert db_guard.get_test_mode() is None
        os.environ["STOCKAI_TEST_MODE"] = "sqlite"
        assert db_guard.get_test_mode() == "sqlite"
        os.environ["STOCKAI_TEST_MODE"] = "postgres"
        assert db_guard.get_test_mode() == "postgres"
    finally:
        if old is not None:
            os.environ["STOCKAI_TEST_MODE"] = old
        else:
            os.environ.pop("STOCKAI_TEST_MODE", None)


def test_orchestrator_detects_unavailable_postgres():
    """Orchestrator in --check-postgres mode must fail when PG is down.

    Runs the orchestrator with a bogus PG host; it must exit nonzero with
    a clear message rather than reporting success.
    """
    result = subprocess.run(
        [
            sys.executable,
            "tests/run_tests.py",
            "--check-postgres",
            "--pg-host",
            "127.0.0.1",
            "--pg-port",
            "1",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0, (
        f"Orchestrator must fail when Postgres is unreachable, "
        f"got returncode 0. stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    combined = (result.stdout + result.stderr).lower()
    assert "postgres" in combined or "connect" in combined or "unreachable" in combined


def test_orchestrator_detects_failed_group():
    """Orchestrator must exit nonzero if any required group fails.

    Runs the SQLite group against a deliberately failing test file
    (a copy with an intentional failure via -k filter that matches
    nothing? No — we use --collect-only on a bad path). Instead we
    verify the orchestrator's exit-code plumbing by invoking it with a
    nonexistent test path, which pytest reports as error (exit != 0).
    """
    import tempfile

    probe_db = os.path.join(tempfile.gettempdir(), f"stockai_orch_probe_{os.getpid()}.db")
    env = dict(os.environ)
    env["STOCKAI_SQLITE_DB_PATH"] = probe_db
    result = subprocess.run(
        [
            sys.executable,
            "tests/run_tests.py",
            "sqlite",
            "--extra-args",
            "--collect-only,-q,tests/test_nonexistent_xyz.py",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    # Either pytest errors (file not found) or the orchestrator reports
    # the failure — both must be nonzero.
    assert result.returncode != 0, (
        f"Orchestrator must propagate pytest failure exit code. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
