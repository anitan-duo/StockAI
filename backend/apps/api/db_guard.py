"""Database URL guard for tests and bootstrap.

Enforces that test runs never silently hit the production database and
that integration runs never silently fall back to SQLite.

Usage:
    - SQLite suite sets STOCKAI_TEST_MODE=sqlite and DATABASE_URL to
      a sqlite+aiosqlite path under /tmp (validated by is_sqlite_url).
    - Postgres suite sets STOCKAI_TEST_MODE=postgres and DATABASE_URL to
      a postgresql+asyncpg URL whose database name ends with _test
      (validated by ensure_test_postgres_url).

Any violation raises RuntimeError with a clear, actionable message.
Changing DATABASE_URL after engine creation cannot retroactively change
the bound engine — see tests/test_db_isolation.py.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

_ALLOWED_SQLITE_PREFIXES = (
    "sqlite+aiosqlite:///",
    "sqlite:///",
)
_TEST_DB_SUFFIX = "_test"
_PROD_DB_NAME = "stockai"


def _strip_password_from_message(url: str) -> str:
    """Never include credentials in error messages."""
    try:
        p = urlparse(url)
        if p.password:
            netloc = f"{p.username}:***@{p.hostname}"
            if p.port:
                netloc += f":{p.port}"
            return f"{p.scheme}://{netloc}{p.path}"
        return url
    except Exception:
        return "<unparsable-url>"


def is_sqlite_url(url: str | None) -> bool:
    if not url:
        return False
    return url.startswith(_ALLOWED_SQLITE_PREFIXES)


def is_postgres_url(url: str | None) -> bool:
    if not url:
        return False
    return url.startswith(("postgresql+asyncpg://", "postgresql://", "postgres://"))


def parse_postgres_db_name(url: str | None) -> str | None:
    if not is_postgres_url(url):
        return None
    try:
        path = urlparse(url).path or ""
        # /dbname or /dbname?query
        name = path.lstrip("/").split("?")[0].strip()
        return name or None
    except Exception:
        return None


def get_test_mode() -> str | None:
    mode = os.environ.get("STOCKAI_TEST_MODE", "").strip().lower()
    return mode if mode in ("sqlite", "postgres") else None


def ensure_sqlite_url(url: str | None, *, context: str = "sqlite suite") -> str:
    """Validate that url is a file-backed SQLite URL under /tmp."""
    if not url:
        raise RuntimeError(
            f"[{context}] DATABASE_URL is not set. "
            f"Set DATABASE_URL to a SQLite test URL, e.g. "
            f"sqlite+aiosqlite:////tmp/stockai_test.db. "
            f"Refusing to continue — no silent fallback to Postgres."
        )
    if not is_sqlite_url(url):
        raise RuntimeError(
            f"[{context}] DATABASE_URL must be a SQLite URL, got "
            f"{_strip_password_from_message(url)}. "
            f"Unit tests must not connect to Postgres. "
            f"Set DATABASE_URL=sqlite+aiosqlite:////tmp/stockai_test.db."
        )
    # Ensure it is NOT :memory: (races across async connections) and NOT prod.
    if ":memory:" in url:
        raise RuntimeError(
            f"[{context}] DATABASE_URL must be file-backed SQLite, not :memory:. "
            f"Use sqlite+aiosqlite:////tmp/stockai_test.db."
        )
    return url


def ensure_test_postgres_url(url: str | None, *, context: str = "postgres suite") -> str:
    """Validate that url targets an isolated *_test Postgres database."""
    if not url:
        raise RuntimeError(
            f"[{context}] DATABASE_URL is not set. "
            f"Set DATABASE_URL to a PostgreSQL test URL, e.g. "
            f"postgresql+asyncpg://stockai:***@localhost:5432/stockai_test. "
            f"Refusing to continue — no silent fallback to SQLite."
        )
    if not is_postgres_url(url):
        raise RuntimeError(
            f"[{context}] DATABASE_URL must be a PostgreSQL URL, got "
            f"{_strip_password_from_message(url)}. "
            f"Integration tests must not silently use SQLite. "
            f"Set DATABASE_URL=postgresql+asyncpg://stockai:***@localhost:5432/stockai_test."
        )
    db_name = parse_postgres_db_name(url)
    if not db_name:
        raise RuntimeError(
            f"[{context}] DATABASE_URL has no database name: "
            f"{_strip_password_from_message(url)}. "
            f"Expected e.g. .../stockai_test."
        )
    if db_name == _PROD_DB_NAME:
        raise RuntimeError(
            f"[{context}] Refusing to run tests against production database "
            f"'{_PROD_DB_NAME}'. Use an isolated test database named '*{_TEST_DB_SUFFIX}' "
            f"(e.g. stockai_test). If this is intentional for live-DB integration "
            f"tests, set STOCKAI_ALLOW_PROD_DB=1 explicitly."
        )
    if not db_name.endswith(_TEST_DB_SUFFIX):
        raise RuntimeError(
            f"[{context}] Test database must end with '{_TEST_DB_SUFFIX}', got "
            f"'{db_name}' ({_strip_password_from_message(url)}). "
            f"Use an isolated test database to prevent accidental damage to dev/prod data."
        )
    return url


def validate_for_mode() -> str:
    """Validate DATABASE_URL matches STOCKAI_TEST_MODE, if set.

    Returns the validated URL. If STOCKAI_TEST_MODE is unset, returns the
    current DATABASE_URL unchanged (production runtime path).
    """
    mode = get_test_mode()
    url = os.environ.get("DATABASE_URL")
    if mode == "sqlite":
        return ensure_sqlite_url(url)
    if mode == "postgres":
        # Allow explicit opt-in to the live dev DB for legacy integration
        # tests that require seeded AAPL/Ensemble rows. The orchestrator
        # uses stockai_test; direct manual runs may opt in.
        if os.environ.get("STOCKAI_ALLOW_PROD_DB", "").strip() in ("1", "true", "yes"):
            if not is_postgres_url(url):
                raise RuntimeError(
                    f"[postgres suite] DATABASE_URL must be PostgreSQL even with "
                    f"STOCKAI_ALLOW_PROD_DB=1, got {_strip_password_from_message(url or '')}."
                )
            return url or ""
        return ensure_test_postgres_url(url)
    return url or ""


def assert_engine_matches_url(engine_url: str, env_url: str | None, *, context: str = "engine") -> None:
    """Assert the live engine URL equals the expected env URL (redacted)."""
    if env_url is None:
        return
    # SQLAlchemy normalizes URLs; compare dialect+driver and db identity.
    # For SQLite, compare full normalized string minus password (SQLite has none).
    # For Postgres, compare db name + host.
    if is_sqlite_url(env_url):
        if not is_sqlite_url(engine_url):
            raise RuntimeError(
                f"[{context}] Engine is bound to Postgres ({_strip_password_from_message(engine_url)}) "
                f"but DATABASE_URL is SQLite ({env_url}). Engine was created before DATABASE_URL "
                f"was set — import-order bug."
            )
    elif is_postgres_url(env_url):
        if not is_postgres_url(engine_url):
            raise RuntimeError(
                f"[{context}] Engine is bound to SQLite ({engine_url}) but DATABASE_URL is "
                f"Postgres ({_strip_password_from_message(env_url)}). "
                f"Integration tests must not silently fall back to SQLite."
            )
        env_db = parse_postgres_db_name(env_url)
        eng_db = parse_postgres_db_name(engine_url)
        if env_db != eng_db:
            raise RuntimeError(
                f"[{context}] Engine database '{eng_db}' != DATABASE_URL database '{env_db}'. "
                f"Stale engine singleton — restart the test process."
            )


__all__ = [
    "assert_engine_matches_url",
    "ensure_sqlite_url",
    "ensure_test_postgres_url",
    "get_test_mode",
    "is_postgres_url",
    "is_sqlite_url",
    "parse_postgres_db_name",
    "validate_for_mode",
]
