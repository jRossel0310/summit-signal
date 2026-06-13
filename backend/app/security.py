"""Password hashing and JWT bearer auth."""
from __future__ import annotations
import datetime as dt
import os

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import models
from .database import get_db

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_ALGO = "HS256"
TOKEN_TTL_DAYS = 7

# Allow tests/dev to run without a configured secret; production sets JWT_SECRET.
_DEV_SECRET = "dev-insecure-secret-change-me-in-production-0123456789"

# auto_error=False so we can return a clean 401 ourselves and support optional auth.
_bearer = HTTPBearer(auto_error=False)


def _secret() -> str:
    return os.environ.get("JWT_SECRET", _DEV_SECRET)


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_token(user_id: int) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + dt.timedelta(days=TOKEN_TTL_DAYS)}
    return jwt.encode(payload, _secret(), algorithm=_ALGO)


def _decode_user_id(token: str) -> int | None:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[_ALGO])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.User:
    if creds is None:
        raise HTTPException(401, "Not authenticated")
    user_id = _decode_user_id(creds.credentials)
    if user_id is None:
        raise HTTPException(401, "Invalid or expired token")
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(401, "User no longer exists")
    return user


def get_current_user_optional(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.User | None:
    if creds is None:
        return None
    user_id = _decode_user_id(creds.credentials)
    if user_id is None:
        return None
    return db.get(models.User, user_id)
