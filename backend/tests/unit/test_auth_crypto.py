"""Unit: auth crypto (hash/verify, JWT roundtrip, token hashing). No DB."""

from datetime import timedelta
from uuid import uuid4

from apps.api.services.auth import auth_service


class _User:
    def __init__(self, email="u@example.com", is_superuser=False):
        self.id = uuid4()
        self.email = email
        self.is_superuser = is_superuser


def test_password_hash_verify_roundtrip():
    hashed = auth_service.get_password_hash("correct-horse-123")
    assert hashed != "correct-horse-123"
    assert auth_service.verify_password("correct-horse-123", hashed) is True
    assert auth_service.verify_password("wrong", hashed) is False


def test_access_token_roundtrip_and_expiry():
    user = _User()
    token = auth_service.create_access_token(user)
    payload = auth_service.decode_token(token)
    assert payload is not None
    assert str(payload.sub) == str(user.id)
    assert payload.type == "access"
    expired = auth_service.create_access_token(user, expires_delta=timedelta(seconds=-1))
    assert auth_service.decode_token(expired) is None
    assert auth_service.decode_token("not-a-token") is None


def test_refresh_token_type_and_hash_stability():
    user = _User()
    token = auth_service.create_refresh_token(user)
    payload = auth_service.decode_token(token)
    assert payload is not None
    assert payload.type == "refresh"
    h1 = auth_service._hash_token(token)
    h2 = auth_service._hash_token(token)
    assert h1 == h2 and len(h1) == 64
