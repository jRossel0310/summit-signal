"""SQLite database setup. All data is stored locally in summit_signal.db."""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

DB_PATH = os.environ.get(
    "SUMMIT_SIGNAL_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "summit_signal.db"),
)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _record):
    """Every connection gets a 30s busy timeout, WAL journaling for better
    write concurrency, and FK enforcement so cascades actually fire."""
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
