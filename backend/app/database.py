"""Database setup. Uses DATABASE_URL when set (Postgres in production), else a
local SQLite file (development). SQLite-specific connect args and pragmas are
applied only on the SQLite dialect."""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker, declarative_base

DEFAULT_SQLITE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "summit_signal.db")


def _build_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        # Render/Neon sometimes provide "postgres://"; SQLAlchemy + psycopg want
        # "postgresql+psycopg://".
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url
    sqlite_path = os.environ.get("SUMMIT_SIGNAL_DB", DEFAULT_SQLITE_PATH)
    return f"sqlite:///{sqlite_path}"


DB_URL = _build_url()
_is_sqlite = make_url(DB_URL).get_backend_name() == "sqlite"

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite else {},
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
