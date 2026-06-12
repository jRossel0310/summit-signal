"""The engine must read DATABASE_URL and only apply SQLite-specific setup on SQLite."""
import importlib


def test_postgres_url_selected(monkeypatch):
    import app.database as database

    # Save the original engine and session factory so other tests are unaffected.
    _orig_engine = database.engine
    _orig_session_local = database.SessionLocal

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    importlib.reload(database)
    try:
        assert database.engine.url.get_backend_name() == "postgresql"
        # No SQLite connect_args leaked onto a Postgres engine.
        assert "check_same_thread" not in database.engine.url.query
    finally:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        importlib.reload(database)  # restore default SQLite engine for other tests
        # The reload creates a fresh engine/SessionLocal.  Overwrite them with the
        # originals so all cached references (app.main, app.routes.*) keep working.
        database.engine = _orig_engine
        database.SessionLocal = _orig_session_local


def test_sqlite_default_when_unset(monkeypatch):
    import app.database as database

    # Save the original engine and session factory so other tests are unaffected.
    _orig_engine = database.engine
    _orig_session_local = database.SessionLocal

    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(database)
    try:
        assert database.engine.url.get_backend_name() == "sqlite"
    finally:
        # Restore originals so cached references in app.main and app.routes keep working.
        database.engine = _orig_engine
        database.SessionLocal = _orig_session_local
