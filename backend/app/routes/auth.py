"""Authentication: signup (invite-gated), login, current user."""
from __future__ import annotations
import hmac
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..schemas import SignupRequest, LoginRequest, TokenResponse, UserOut
from ..security import hash_password, verify_password, create_token, get_current_user
from ..seed import seed_for_user

router = APIRouter()

MIN_PASSWORD_LEN = 8


def _normalize_email(email: str) -> str:
    return email.strip().lower()


@router.post("/auth/signup", response_model=TokenResponse)
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    expected = os.environ.get("SIGNUP_CODE", "")
    if not expected or not hmac.compare_digest(body.invite_code, expected):
        raise HTTPException(400, "Invalid invite code")
    if len(body.password) < MIN_PASSWORD_LEN:
        raise HTTPException(400, f"Password must be at least {MIN_PASSWORD_LEN} characters")
    email = _normalize_email(body.email)
    if not email or "@" not in email:
        raise HTTPException(400, "A valid email is required")
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(409, "An account with that email already exists")
    user = models.User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    seed_for_user(db, user.id)
    return TokenResponse(token=create_token(user.id), user=UserOut(id=user.id, email=user.email))


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    email = _normalize_email(body.email)
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return TokenResponse(token=create_token(user.id), user=UserOut(id=user.id, email=user.email))


@router.get("/auth/me", response_model=UserOut)
def me(user: models.User = Depends(get_current_user)):
    return UserOut(id=user.id, email=user.email)
