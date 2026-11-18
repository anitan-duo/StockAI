"""Unit: TrustedHostMiddleware + ALLOWED_HOSTS parsing. No DB/network (DB guard)."""

from fastapi.testclient import TestClient

from apps.api.config import Settings
from apps.api.main import app


def test_allowed_hosts_defaults_include_testclient():
    s = Settings()
    assert "testserver" in s.allowed_hosts
    assert "localhost" in s.allowed_hosts


def test_allowed_hosts_comma_separated():
    s = Settings(ALLOWED_HOSTS="api.example.com, example.com")
    assert s.allowed_hosts == ["api.example.com", "example.com"]


def test_allowed_hosts_json_array():
    s = Settings(ALLOWED_HOSTS='["a.example.com"]')
    assert s.allowed_hosts == ["a.example.com"]


def test_trusted_host_allowed():
    c = TestClient(app)
    r = c.get("/", headers={"host": "localhost"})
    assert r.status_code == 200


def test_trusted_host_rejected():
    c = TestClient(app)
    r = c.get("/", headers={"host": "evil.example.com"})
    assert r.status_code == 400
