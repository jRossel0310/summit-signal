"""SQLite database setup. All data is stored locally in summit_signal.db."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DB_PATH = os.environ.get(
    "SUMMIT_SIGNAL_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "summit_signal.db"),
)

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
