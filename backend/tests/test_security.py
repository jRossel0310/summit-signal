"""Password hashing and token round-trip."""
import datetime as dt

import jwt
from app import security


def test_password_hash_roundtrip():
    h = security.hash_password("password123")
    assert h != "password123"
    assert security.verify_password("password123", h)
    assert not security.verify_password("wrong", h)


def test_token_roundtrip():
    token = security.create_token(42)
    assert security._decode_user_id(token) == 42


def test_garbage_token_returns_none():
    assert security._decode_user_id("not-a-jwt") is None


def test_expired_token_returns_none(monkeypatch):
    # Build a token that expired in the past, signed with the same secret.
    past = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    token = jwt.encode({"sub": "5", "exp": past}, security._secret(), algorithm="HS256")
    assert security._decode_user_id(token) is None
