"""Reliability fixes: SQLite PRAGMAs and _run_check guards so a deleted trip
never leaves a check stuck 'running'."""
from sqlalchemy import text

from app.database import engine
from app.agent import jobs
from app import models
from app.database import SessionLocal


def test_sqlite_pragmas_applied():
    with engine.connect() as conn:
        busy = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
        fk = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert int(busy) >= 30000
    assert int(fk) == 1


def test_run_check_marks_failed_when_trip_missing():
    # Simulate the orphaned-row race: a check whose trip no longer exists.
    # FK enforcement (now ON globally) rejects a dangling trip_id, so we drop
    # the pragma for just this insert to manufacture the orphan the worker must
    # survive. _run_check must mark it failed without running any connectors.
    db = SessionLocal()
    try:
        db.execute(text("PRAGMA foreign_keys=OFF"))
        check = models.ConditionCheck(trip_id=999_999, status="running")
        db.add(check)
        db.commit()
        check_id = check.id
    finally:
        db.close()

    jobs._run_check(check_id)  # must not raise and must not hang

    db = SessionLocal()
    try:
        refreshed = db.get(models.ConditionCheck, check_id)
        assert refreshed.status == "failed"
    finally:
        db.close()


def test_run_check_returns_quietly_when_check_missing():
    jobs._run_check(999_999)  # nonexistent check id — must be a no-op, no exception
