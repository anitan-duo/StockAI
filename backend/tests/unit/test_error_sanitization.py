"""Regression tests: client-facing error bodies must not leak internals.

SEC regression — the ValueError/PermissionError exception handlers used to
return ``str(exc)`` verbatim. Raise sites across the codebase can embed
internal filesystem paths, SQL fragments, connection strings, library names,
or auth detail. These tests prove the sanitizer suppresses those wholesale
while preserving ordinary user-input validation messages, and that the
request ID is echoed for operator correlation.
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from apps.api.main import _safe_detail, app


def _client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# _safe_detail classifier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "msg",
    [
        # internal filesystem paths / artifact locations
        "artifact missing: /srv/app/model_artifacts/real/ensemble/v1.0/model.pkl",
        "candidate artifact file missing at /app/backend/model_artifacts/x.pkl",
        # SQL fragments
        "relation \"predictions\" does not exist at line 1",
        "SELECT * FROM users WHERE email = 'x'",
        # connection strings / DSNs
        "could not connect: postgresql+asyncpg://stockai:stockai@localhost:5432/stockai",
        "redis://user:pass@valkey:6379/0 failed",
        # secret-bearing assignments
        "SECRET_KEY must be set to a unique value of at least 32 characters",
        "invalid api_key supplied for provider finnhub",
        # library / traceback fragments
        "sqlalchemy.exc.OperationalError: connection refused",
        'File "/app/backend/apps/api/main.py", line 42, in handler',
        "Traceback (most recent call last):",
    ],
)
def test_sensitive_messages_are_suppressed_wholesale(msg: str):
    assert (
        _safe_detail(ValueError(msg))
        == "Request could not be processed. Reference ID has been logged."
    ), f"leaked: {msg}"


@pytest.mark.parametrize(
    "msg",
    [
        "Email already registered",
        "Invalid credentials",
        "password must be at least 8 characters",
        "horizon must be one of 1d, 5d, 10d",
        "symbol is required",
    ],
)
def test_user_input_validation_messages_survive(msg: str):
    """Ordinary validation feedback must stay legible to the client."""
    assert _safe_detail(ValueError(msg)) == msg


# ---------------------------------------------------------------------------
# End-to-end through the app
# ---------------------------------------------------------------------------

def _raise_app(exc: Exception) -> FastAPI:
    test_app = FastAPI()

    @test_app.get("/boom")
    async def boom() -> dict:
        raise exc

    # Reuse the production handlers by mounting them on the test app.
    from apps.api.main import app as production_app

    for exc_type in (ValueError, PermissionError, Exception):
        handler = production_app.exception_handlers.get(exc_type)
        if handler is not None:
            test_app.add_exception_handler(exc_type, handler)
    # The generic 500 handler must be reachable; TestClient re-raises by default.
    return test_app


def _client_for_app(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _no_raise():
    return None


def test_value_error_handler_suppresses_path_leak_e2e():
    client = _client_for_app(_raise_app(ValueError("artifact missing: /app/backend/model_artifacts/real/ensemble/v1.0/model.pkl")))
    r = client.get("/boom")
    assert r.status_code == 400
    body = r.json()
    assert body["detail"] == "Request could not be processed. Reference ID has been logged."
    assert "model_artifacts" not in body["detail"]
    assert "/app/" not in body["detail"]


def test_value_error_handler_keeps_validation_message_e2e():
    client = _client_for_app(_raise_app(ValueError("horizon must be one of 1d, 5d, 10d")))
    r = client.get("/boom")
    assert r.status_code == 400
    assert r.json()["detail"] == "horizon must be one of 1d, 5d, 10d"


def test_permission_error_handler_sanitized_e2e():
    client = _client_for_app(_raise_app(PermissionError("forbidden: /etc/passwd")))
    r = client.get("/boom")
    assert r.status_code == 403
    assert r.json()["detail"] == "Request could not be processed. Reference ID has been logged."


def test_unhandled_exception_handler_is_generic():
    client = _client_for_app(_raise_app(RuntimeError("db password=hunter2 sqlalchemy.exc.OperationalError")))
    r = client.get("/boom")
    assert r.status_code == 500
    assert r.json()["detail"] == "Internal server error"


def test_request_id_echoed_in_error_response():
    client = _client()
    r = client.get("/api/v1/nonexistent-path-404", headers={"x-request-id": "test-corr-id-123"})
    # 404 path exercises middleware; the header must be present on responses.
    assert r.headers.get("x-request-id") == "test-corr-id-123"


def test_generic_500_carries_request_id_header():
    client = _client_for_app(_raise_app(RuntimeError("boom")))
    r = client.get("/boom", headers={"x-request-id": "corr-789"})
    assert r.status_code == 500
    assert r.headers.get("x-request-id") == "corr-789"
