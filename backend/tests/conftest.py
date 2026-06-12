"""Shared pytest fixtures. The `session` fixture gives each test an isolated
in-memory SQLite session with all tables created — no app, no seeding, no
network. Use it for model/cascade and service-layer tests."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models  # noqa: F401  (import registers the ORM mappers on Base)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sess = sessionmaker(bind=engine)()
    try:
        yield sess
    finally:
        sess.close()
        Base.metadata.drop_all(engine)
