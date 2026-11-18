"""Unit: auth rate-limit throttle + generic auth responses. No DB/network (DB guard).

Verifies:
- `_check_throttle` returns 429 once attempts exceed the configured limit
  (Valkey mocked via a fake async client), and is fail-open when Valkey is
  unavailable.
- register/login return generic error details (no account-existence oracle).
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.api.routes import auth as auth_route
from apps.api.routes.auth import _check_throttle


def _fake_request(email: str = "u@example.com"):
    req = MagicMock()
    req.client = MagicMock()
    req.client.host = "127.0.0.1"
    return req


def _patch_valkey(client):
    async def fake_get_valkey():
        return client

    return patch("services.cache.get_valkey", fake_get_valkey)


class _FakeValkey:
    def __init__(self):
        self.count = 0
        self.expired = None

    async def incr(self, key):
        self.count += 1
        return self.count

    async def expire(self, key, ttl):
        self.expired = ttl
        return True


def test_throttle_allows_under_limit_and_sets_expiry():
    client = _FakeValkey()
    with _patch_valkey(client):
        asyncio.run(_check_throttle(_fake_request(), "login", "u@example.com", max_attempts=3))
    assert client.count == 1
    assert client.expired == auth_route.settings.auth_throttle_window_seconds


def test_throttle_blocks_over_limit():
    client = _FakeValkey()
    client.count = 3  # at limit; next incr -> 4 > 3
    with _patch_valkey(client), pytest.raises(HTTPException) as exc:
        asyncio.run(_check_throttle(_fake_request(), "register", "u@example.com", max_attempts=3))
    assert exc.value.status_code == 429


def test_throttle_fail_open_when_valkey_unavailable():
    with _patch_valkey(None):
        # Must not raise when Valkey is down.
        asyncio.run(_check_throttle(_fake_request(), "login", "u@example.com", max_attempts=1))


def test_throttle_fail_open_on_valkey_error():
    class _Boom:
        async def incr(self, key):
            raise ConnectionError("valkey down")

    with _patch_valkey(_Boom()):
        asyncio.run(_check_throttle(_fake_request(), "login", "u@example.com", max_attempts=1))


def test_login_generic_error_detail():
    async def boom(*a, **kw):
        raise ValueError("Invalid credentials")

    req = _fake_request()
    req.headers = {"user-agent": "test"}
    with _patch_valkey(None), patch.object(auth_route.auth_service, "login", boom):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(auth_route.login(MagicMock(email="a@b.c", password="x", remember_me=False), req))
    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid credentials"


def test_register_generic_error_detail():
    async def boom(*a, **kw):
        raise ValueError("Email already registered")

    req = _fake_request()
    req.headers = {}
    data = MagicMock(email="dup@example.com")
    with _patch_valkey(None), patch.object(auth_route.auth_service, "register", boom):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(auth_route.register(data, req))
    assert exc.value.status_code == 400
    assert exc.value.detail == "Registration could not be completed"
