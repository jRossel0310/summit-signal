"""Shared pytest fixtures. The `session` fixture gives each test an isolated
in-memory SQLite session with all tables created; no app, no seeding, no
network. Use it for model/cascade and service-layer tests."""
import os
import tempfile

# Bind the shared app engine to a throwaway DB for the whole test session.
# conftest is imported before any test module, so this guarantees no test
# (including ones that import the real engine/app) ever touches summit_signal.db.
os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "summit_test.db"))
os.environ.setdefault("SIGNUP_CODE", "test-invite-code")

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models  # noqa: F401  (import registers the ORM mappers on Base)


@pytest.fixture(scope="session", autouse=True)
def _create_app_schema():
    """Create the schema on the shared app engine's throwaway DB once per
    session, so tests that use the real engine/SessionLocal directly (e.g.
    test_concurrency) work even when run in isolation, not just after another
    test happens to have spun up the app and created the tables first."""
    from app.database import engine

    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine)()
    try:
        yield sess
    finally:
        sess.close()
        Base.metadata.drop_all(engine)


def signup_and_token(client, email="user@example.com", password="password123"):
    """Sign up a fresh user via the API and return (token, user_id, headers)."""
    r = client.post("/auth/signup", json={
        "email": email, "password": password, "invite_code": os.environ["SIGNUP_CODE"]})
    assert r.status_code == 200, r.text
    body = r.json()
    headers = {"Authorization": f"Bearer {body['token']}"}
    return body["token"], body["user"]["id"], headers
