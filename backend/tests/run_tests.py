#!/usr/bin/env python3
"""Unified test orchestrator — Phase 2 §4.

Runs SQLite and PostgreSQL suites in SEPARATE pytest processes with
deterministic DATABASE_URL established before any app import.

    python tests/run_tests.py                # all suites (sqlite + postgres)
    python tests/run_tests.py sqlite         # SQLite unit/ML only
    python tests/run_tests.py postgres       # Postgres integration only
    python tests/run_tests.py sqlite -- -k pattern   # pass through to pytest

Exit code is NONZERO if any required group fails or is blocked (e.g.
Postgres unreachable). A partially completed run is never reported as a
successful full-suite run.

Suite definitions:
  - sqlite:   tests/test_db_isolation.py tests/test_backtesting.py (non-integration)
              tests/unit/ tests/ml/ tests/backtesting/
              with STOCKAI_TEST_MODE=sqlite, file-backed SQLite DB.
              Excludes tests/integration/ (Postgres) and
              TestBacktestValidation (marked integration).
  - postgres: tests/integration/ + tests/test_backtesting.py::TestBacktestValidation
              with STOCKAI_TEST_MODE=postgres, isolated stockai_test DB.
              Requires live Postgres (docker start stockai-postgres).

Postgres test-DB preparation:
  - If stockai_test does not exist, it is created.
  - Schema is created via alembic upgrade head (or Base.metadata.create_all
    fallback if alembic is unavailable).
  - Synthetic fixtures (markets/exchanges/19 instruments/daily bars from
    2025-01-02, Ensemble v1.0 + pinned champion, fresh predictions) are
    inserted via tests/fixtures_seed.py — fully deterministic and
    self-contained. No production data is read or dumped.

This script never touches the production `stockai` database at all.
It only writes to the isolated `stockai_test` database.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Allow an isolated path for orchestrator self-tests: the subprocess must
# never unlink the database file a parent test process is still using.
SQLITE_DB_PATH = os.environ.get("STOCKAI_SQLITE_DB_PATH") or os.environ.get(
    "STOCKAI_TEST_DB_PATH", "/tmp/stockai_test.db"
)
SQLITE_URL = f"sqlite+aiosqlite:///{SQLITE_DB_PATH}"
PG_USER = "stockai"
PG_PASS = "stockai"
PG_HOST = "localhost"
PG_PORT = 5432
PG_TEST_DB = "stockai_test"
PG_TEST_URL = f"postgresql+asyncpg://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_TEST_DB}"

SQLITE_PATHS = [
    "tests/test_db_isolation.py",
    "tests/test_backtesting.py",
    "tests/unit",
    "tests/ml",
    "tests/backtesting",
]
POSTGRES_PATHS = [
    "tests/integration",
    "tests/test_backtesting.py::TestBacktestValidation",
]


def log(msg: str) -> None:
    print(f"[run_tests] {msg}", flush=True)


def check_postgres(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_sqlite_clean() -> None:
    try:
        if os.path.exists(SQLITE_DB_PATH):
            os.unlink(SQLITE_DB_PATH)
            log(f"removed stale {SQLITE_DB_PATH}")
    except OSError as exc:
        log(f"WARN: could not remove {SQLITE_DB_PATH}: {exc}")


def run_pytest(paths: list[str], env: dict[str, str], extra_args: list[str]) -> int:
    cmd = [sys.executable, "-m", "pytest"] + paths + extra_args
    log(f"running: {' '.join(cmd)}")
    env_full = dict(os.environ)
    env_full.update(env)
    # conftest eviction: ensure __pycache__ doesn't leak stale modules.
    result = subprocess.run(cmd, cwd=REPO_ROOT, env=env_full)
    return result.returncode


def pg_exec(sql: str, db: str = "postgres") -> subprocess.CompletedProcess:
    """Execute SQL against the given database (defaults to 'postgres' for meta commands)."""
    cmd = [
        "docker",
        "exec",
        "-i",
        "stockai-postgres",
        "psql",
        "-U",
        PG_USER,
        "-d",
        db,
        "-v",
        "ON_ERROR_STOP=1",
        "-q",
        "-c",
        sql,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def ensure_test_db() -> int:
    """Create stockai_test, migrate, and seed synthetic fixtures. Returns 0 or nonzero."""
    log("ensuring isolated Postgres test database 'stockai_test'...")
    # Drop DB if exists to ensure pristine state
    log(f"resetting database {PG_TEST_DB} for integration tests")
    # psql -d postgres to drop/create other DBs
    pg_exec(f"DROP DATABASE IF EXISTS {PG_TEST_DB} WITH (FORCE)", db="postgres")

    # Create DB
    log(f"creating database {PG_TEST_DB}")
    r = pg_exec(f"CREATE DATABASE {PG_TEST_DB}", db="postgres")
    if r.returncode != 0:
        log(f"ERROR creating test DB: {r.stderr.strip()}")
        return 1

    # Run alembic migrations against the TEST DB only.
    log("running alembic upgrade head against stockai_test...")
    env = dict(os.environ)
    env["DATABASE_URL"] = PG_TEST_URL
    env["STOCKAI_TEST_MODE"] = "postgres"
    env["SECRET_KEY"] = "stockai-test-secret-key-0123456789abcdef"
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "database/migrations/alembic.ini", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if r.returncode != 0:
        log(f"alembic failed (exit {r.returncode}):")
        log(r.stdout[-3000:])
        log(r.stderr[-3000:])
        # Fall back to metadata.create_all via a small script.
        log("falling back to Base.metadata.create_all for stockai_test...")
        script = (
            "import os, asyncio; "
            "os.environ['DATABASE_URL'] = os.environ.get('DATABASE_URL', ''); "
            "from apps.api.models.base import Base; import apps.api.models; "
            "from apps.api.database import engine; "
            "async def m():\n"
            "    async with engine.begin() as c:\n"
            "        await c.run_sync(Base.metadata.create_all)\n"
            "asyncio.run(m())\n"
        )
        r2 = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r2.returncode != 0:
            log(f"create_all fallback failed: {r2.stderr.strip()[-2000:]}")
            return 1

    # Seed: synthetic fixtures (no prod reads). The seeder is idempotent — if
    # Ensemble already exists it reports seeded=False and leaves rows alone.
    log("seeding stockai_test with synthetic fixtures (tests/fixtures_seed.py)...")
    r = seed_with_fixtures(env)
    if r != 0:
        log(f"ERROR: synthetic fixture seeding failed (exit {r})")
        return 1
    return 0


def seed_with_fixtures(env: dict[str, str]) -> int:
    """Run tests/fixtures_seed.py against the test DB only.

    No production database is ever connected to: DATABASE_URL points at
    stockai_test and STOCKAI_TEST_MODE=postgres makes db_guard refuse the
    production DB unless explicitly allowed (never set here).
    """
    script_path = os.path.join(REPO_ROOT, "tests", "fixtures_seed.py")
    r = subprocess.run(
        [sys.executable, script_path],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    log(r.stdout.strip()[-1200:])
    if r.returncode != 0:
        log(f"fixture seeder failed: {r.stderr.strip()[-2000:]}")
        return r.returncode
    if "'seeded': False" in r.stdout or '"seeded": False' in r.stdout or "seeded': False" in r.stdout:
        log("fixtures already present — skipping (idempotent)")
    return 0


def run_sqlite(extra_args: list[str]) -> int:
    ensure_sqlite_clean()
    env = {
        "STOCKAI_TEST_MODE": "sqlite",
        "DATABASE_URL": SQLITE_URL,
        "STOCKAI_TEST_DB_PATH": SQLITE_DB_PATH,
        "REDIS_URL": "redis://localhost:6379/0",
        "VALKEY_URL": "redis://localhost:6379/0",
        "SECRET_KEY": "stockai-test-secret-key-0123456789abcdef",
    }
    # Exclude integration-marked tests from test_backtesting.py in sqlite mode.
    pytest_args = list(extra_args)
    if "-m" not in pytest_args:
        pytest_args += ["-m", "not integration"]
    return run_pytest(SQLITE_PATHS, env, pytest_args)


def run_postgres(extra_args: list[str]) -> int:
    if not check_postgres(PG_HOST, PG_PORT):
        log(
            f"ERROR: PostgreSQL is not reachable at {PG_HOST}:{PG_PORT}. "
            f"Start it with: docker start stockai-postgres "
            f"(or: docker compose up -d postgres). "
            f"Integration tests will NOT fall back to SQLite."
        )
        return 2
    log(f"PostgreSQL reachable at {PG_HOST}:{PG_PORT}")
    # Prepare test DB (create/migrate/seed) — writes only to stockai_test.
    if ensure_test_db() != 0:
        log("ERROR: failed to prepare stockai_test database")
        return 2
    env = {
        "STOCKAI_TEST_MODE": "postgres",
        "DATABASE_URL": PG_TEST_URL,
        "REDIS_URL": "redis://localhost:6379/0",
        "VALKEY_URL": "redis://localhost:6379/0",
        "SECRET_KEY": "stockai-test-secret-key-0123456789abcdef",
    }
    # Also run TestBacktestValidation which is misplaced under tests/
    # (marked integration) — it needs the seeded Postgres DB.
    return run_pytest(POSTGRES_PATHS, env, list(extra_args))


def main() -> int:
    parser = argparse.ArgumentParser(description="StockAI unified test orchestrator")
    parser.add_argument(
        "suite",
        nargs="?",
        default="all",
        choices=["all", "sqlite", "postgres"],
        help="which suite to run (default: all)",
    )
    parser.add_argument("--check-postgres", action="store_true", help="only verify Postgres reachability")
    parser.add_argument("--pg-host", default=PG_HOST)
    parser.add_argument("--pg-port", type=int, default=PG_PORT)
    parser.add_argument("--prepare-postgres", action="store_true", help="create/migrate/seed stockai_test and exit")
    parser.add_argument("extra", nargs=argparse.REMAINDER, help="extra args passed to pytest (after --)")
    args = parser.parse_args()

    extra_args = list(args.extra)
    if extra_args and extra_args[0] == "--":
        extra_args = extra_args[1:]

    # Re-parse for --pg-host/--pg-port on --check-postgres (already handled).

    if args.check_postgres:
        if check_postgres(args.pg_host, args.pg_port):
            log(f"PostgreSQL reachable at {args.pg_host}:{args.pg_port}")
            return 0
        log(f"ERROR: PostgreSQL unreachable at {args.pg_host}:{args.pg_port}. Start with: docker start stockai-postgres")
        return 2

    if args.prepare_postgres:
        if not check_postgres(args.pg_host, args.pg_port):
            log(f"ERROR: PostgreSQL unreachable at {args.pg_host}:{args.pg_port}")
            return 2
        return ensure_test_db()

    exit_code = 0
    groups: list[tuple[str, int]] = []

    if args.suite in ("all", "sqlite"):
        log("=== SUITE: sqlite (unit/ML, SQLite) ===")
        code = run_sqlite(extra_args)
        groups.append(("sqlite", code))
        if code != 0:
            exit_code = 1

    if args.suite in ("all", "postgres"):
        log("=== SUITE: postgres (integration, PostgreSQL) ===")
        code = run_postgres(extra_args)
        groups.append(("postgres", code))
        if code != 0:
            exit_code = code if code != 1 else 1

    log(f"=== SUMMARY: {groups} ===")
    if exit_code != 0:
        log("RESULT: FAIL (one or more required groups failed or were blocked)")
    else:
        log("RESULT: PASS (all required groups passed)")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
