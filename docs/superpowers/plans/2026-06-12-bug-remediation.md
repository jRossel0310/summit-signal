# SummitSignal Bug Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all verified bugs from the 2026-06-12 audit across 7 themed areas — persistence/cascade, concurrency hardening, risk-engine completeness, report robustness, route/settings correctness, connector correctness, and frontend state — each with a regression test where practical.

**Architecture:** The fixes are surgical edits to an existing FastAPI + SQLite (SQLAlchemy) backend and a React + TypeScript + MapLibre frontend. Backend tests are pure-function or in-memory-session `pytest` tests added alongside the existing offline suite; concurrency/PRAGMA tests use the app's real engine. The frontend has no test harness, so its fixes are verified by documented manual repro plus one optional Vitest test.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2.x, APScheduler, pytest, httpx; React 18, TypeScript, Vite, MapLibre GL.

**Reference spec:** `docs/superpowers/specs/2026-06-12-bug-remediation-design.md`

**Conventions:**
- Run backend tests from the `backend/` directory: `python -m pytest tests/ -q`.
- Run a single test: `python -m pytest tests/test_<file>.py::<name> -v`.
- Commit after each task. Commit message style: `fix(<area>): <summary>`.

---

## File Structure

**Backend — modified:**
- `backend/app/models.py` — add `ForeignKey(..., ondelete="CASCADE")` and cascade relationships (Batch 1).
- `backend/app/routes/trips.py` — `delete_trip` cascade, `update_trip` field-clearing, `print_report` 404 (Batches 1, 4, 5).
- `backend/app/database.py` — SQLite `timeout` + PRAGMA event listener (Batch 2).
- `backend/app/agent/scheduler.py` — bounded job config (Batch 2).
- `backend/app/agent/jobs.py` — None-guards + worker semaphore (Batch 2).
- `backend/app/services/risk_engine.py` — completeness over enabled connectors (Batch 3).
- `backend/app/services/report_generator.py` — defensive `.get()` rendering, zero handling (Batch 4).
- `backend/app/services/settings_service.py` — keep default on parse failure (Batch 5).
- `backend/app/connectors/elevation_adjusted.py` — `is None` checks (Batch 6).
- `backend/app/connectors/usgs_elevation.py` — correct fallback failure label (Batch 6).

**Backend — created:**
- `backend/tests/conftest.py` — in-memory `session` fixture.
- `backend/tests/test_persistence.py`, `test_concurrency.py`, `test_risk_completeness.py`, `test_report_robustness.py`, `test_routes_settings.py`, `test_connectors.py`.

**Frontend — modified:**
- `frontend/src/App.tsx` — polling lifecycle on trip-switch, `onTripUpdated`/`onTripDeleted` sync (Batch 7).
- `frontend/src/components/ConditionDashboard.tsx` — guard `elevation_m` (Batch 7).
- `frontend/src/components/TripDetail.tsx` — guard GPX display values (Batch 7).
- `frontend/src/components/SearchBar.tsx` — stable list key (Batch 7).

---

## Task 0: Initialize git and test scaffolding

This repo is not yet a git repository, so per-task commits need a repo first.

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `.gitignore` (repo root)

- [ ] **Step 1: Initialize the repository**

Run from the repo root `c:/Users/jacob/summit-signal`:
```bash
git init
git add -A
git commit -m "chore: snapshot before bug remediation"
```
Expected: a repository with one initial commit.

- [ ] **Step 2: Add a .gitignore so build/db artifacts aren't tracked**

Create `.gitignore` at the repo root:
```gitignore
# Python
__pycache__/
*.pyc
.venv/
backend/summit_signal.db
backend/*.db
backend/*.db-wal
backend/*.db-shm

# Node
frontend/node_modules/
frontend/dist/

# Test artifacts
.pytest_cache/
```

- [ ] **Step 3: Create the in-memory session fixture for unit tests**

Create `backend/tests/conftest.py`:
```python
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
```

- [ ] **Step 4: Verify the existing suite still passes and the fixture imports**

Run from `backend/`:
```bash
python -m pytest tests/ -q
```
Expected: all existing tests PASS, no collection errors from the new `conftest.py`.

- [ ] **Step 5: Commit**

```bash
git add .gitignore backend/tests/conftest.py
git commit -m "chore: add gitignore and in-memory session test fixture"
```

---

## Task 1: Cascade integrity on trip deletion (Batch 1)

**Bug:** `delete_trip` uses a bulk `Query.delete()` that bypasses ORM cascades, orphaning `ConnectorResult`/`RiskFlag`/`AiSummary`/`SavedReport`. `AiSummary` and `SavedReport` also lack cascade relationships, and `SavedReport.condition_check_id` is not even a `ForeignKey`.

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/routes/trips.py:91-99`
- Test: `backend/tests/test_persistence.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_persistence.py`:
```python
"""Deleting a trip must remove every descendant row (no orphans)."""
from app import models


def _make_full_trip(session):
    trip = models.Trip(name="T", latitude=46.0, longitude=-121.0,
                       start_date="2026-07-01", end_date="2026-07-03")
    session.add(trip)
    session.flush()
    check = models.ConditionCheck(trip_id=trip.id, status="complete")
    session.add(check)
    session.flush()
    session.add(models.ConnectorResult(condition_check_id=check.id,
                                       connector_name="nws_weather", status="success"))
    session.add(models.RiskFlag(condition_check_id=check.id, title="x"))
    session.add(models.AiSummary(condition_check_id=check.id, summary_markdown="s"))
    session.add(models.SavedReport(trip_id=trip.id, condition_check_id=check.id, html="<p>r</p>"))
    session.commit()
    return trip.id


def test_delete_trip_cascades_all_children(session):
    trip_id = _make_full_trip(session)
    trip = session.get(models.Trip, trip_id)
    session.delete(trip)
    session.commit()

    assert session.query(models.ConditionCheck).count() == 0
    assert session.query(models.ConnectorResult).count() == 0
    assert session.query(models.RiskFlag).count() == 0
    assert session.query(models.AiSummary).count() == 0
    assert session.query(models.SavedReport).count() == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run from `backend/`:
```bash
python -m pytest tests/test_persistence.py -v
```
Expected: FAIL — `AiSummary` and `SavedReport` rows remain (no cascade relationship), so counts are 1, not 0.

- [ ] **Step 3: Add cascade relationships and ondelete to the models**

In `backend/app/models.py`, update `ConditionCheck.trip_id` and add an `ai_summaries` relationship:
```python
class ConditionCheck(Base):
    __tablename__ = "condition_checks"
    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String, default="running")  # running | complete | failed
    overall_concern_status = Column(String, nullable=True)
    data_completeness_score = Column(Float, nullable=True)  # 0..1
    summary_text = Column(Text, nullable=True)

    trip = relationship("Trip", back_populates="condition_checks")
    connector_results = relationship(
        "ConnectorResult", back_populates="condition_check", cascade="all, delete-orphan"
    )
    risk_flags = relationship(
        "RiskFlag", back_populates="condition_check", cascade="all, delete-orphan"
    )
    ai_summaries = relationship(
        "AiSummary", back_populates="condition_check", cascade="all, delete-orphan"
    )
```

Add `ondelete="CASCADE"` to the child FKs:
```python
class ConnectorResult(Base):
    __tablename__ = "connector_results"
    id = Column(Integer, primary_key=True)
    condition_check_id = Column(
        Integer, ForeignKey("condition_checks.id", ondelete="CASCADE"), nullable=False)
```
```python
class RiskFlag(Base):
    __tablename__ = "risk_flags"
    id = Column(Integer, primary_key=True)
    condition_check_id = Column(
        Integer, ForeignKey("condition_checks.id", ondelete="CASCADE"), nullable=False)
```

Give `AiSummary` a real FK + back-reference:
```python
class AiSummary(Base):
    __tablename__ = "ai_summaries"
    id = Column(Integer, primary_key=True)
    condition_check_id = Column(
        Integer, ForeignKey("condition_checks.id", ondelete="CASCADE"), nullable=False)
    generator = Column(String, default="rule_based")  # rule_based | ollama:<model>
    summary_markdown = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)

    condition_check = relationship("ConditionCheck", back_populates="ai_summaries")
```

Make `SavedReport.condition_check_id` a real FK and cascade saved reports from the trip:
```python
class SavedReport(Base):
    __tablename__ = "saved_reports"
    id = Column(Integer, primary_key=True)
    trip_id = Column(Integer, ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    condition_check_id = Column(
        Integer, ForeignKey("condition_checks.id", ondelete="CASCADE"), nullable=True)
    html = Column(Text, default="")
    created_at = Column(DateTime, default=utcnow)
```

Add the `saved_reports` cascade relationship to `Trip` (so ORM deletes them when the trip is deleted):
```python
    gpx_route = relationship("GpxRoute", foreign_keys=[gpx_route_id])
    condition_checks = relationship(
        "ConditionCheck", back_populates="trip", cascade="all, delete-orphan"
    )
    saved_reports = relationship(
        "SavedReport", cascade="all, delete-orphan"
    )
```

> Note: ORM cascade (`delete-orphan`) handles the happy path regardless of DB-level FK enforcement. The `ondelete="CASCADE"` clauses are belt-and-braces for when `PRAGMA foreign_keys=ON` is active (Task 2). `SavedReport` is cascaded only from `Trip` at the ORM layer to avoid multi-parent delete-orphan conflicts; its `condition_check_id` orphan case is covered by the DB-level cascade.

- [ ] **Step 4: Fix `delete_trip` to use the ORM cascade**

In `backend/app/routes/trips.py`, replace the bulk delete:
```python
@router.delete("/trips/{trip_id}")
def delete_trip(trip_id: int, db: Session = Depends(get_db)):
    trip = db.get(models.Trip, trip_id)
    if not trip:
        raise HTTPException(404, "Trip not found")
    db.delete(trip)  # ORM cascade removes checks, connector results, flags, summaries, reports
    db.commit()
    return {"deleted": trip_id}
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
python -m pytest tests/test_persistence.py -v
```
Expected: PASS — all descendant counts are 0.

- [ ] **Step 6: Run the full suite to check for regressions**

```bash
python -m pytest tests/ -q
```
Expected: all PASS (the existing `test_seeded_trips_and_crud` still deletes a trip successfully).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models.py backend/app/routes/trips.py backend/tests/test_persistence.py
git commit -m "fix(persistence): cascade-delete all trip descendants; add FKs to AiSummary/SavedReport"
```

---

## Task 2: Concurrency & reliability hardening (Batch 2)

**Bugs:** (a) SQLite has no busy timeout → concurrent worker commits hit `database is locked`; (b) the scheduled job has no `max_instances`/`coalesce`/`misfire_grace_time` and spawns one unmanaged thread per trip; (c) `_run_check` never None-checks `check`/`trip`, leaving a check stuck `running` forever.

**Files:**
- Modify: `backend/app/database.py`
- Modify: `backend/app/agent/scheduler.py:22-29`
- Modify: `backend/app/agent/jobs.py:42-150`
- Test: `backend/tests/test_concurrency.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_concurrency.py`:
```python
"""Reliability fixes: SQLite PRAGMAs, bounded scheduler job, and _run_check
guards so a deleted trip never leaves a check stuck 'running'."""
from app.database import engine
from app.agent import jobs, scheduler
from app import models
from app.database import SessionLocal


def test_sqlite_pragmas_applied():
    with engine.connect() as conn:
        busy = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
        fk = conn.exec_driver_sql("PRAGMA foreign_keys").scalar()
    assert int(busy) >= 30000
    assert int(fk) == 1


def test_scheduled_job_is_bounded():
    scheduler.set_interval_hours(1)
    try:
        job = scheduler.scheduler.get_job(scheduler.JOB_ID)
        assert job is not None
        assert job.max_instances == 1
        assert job.coalesce is True
    finally:
        scheduler.set_interval_hours(0)  # remove the job again


def test_run_check_marks_failed_when_trip_missing():
    db = SessionLocal()
    try:
        # A check whose trip does not exist (simulates a deleted trip).
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
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_concurrency.py -v
```
Expected: FAIL — PRAGMAs not set (busy_timeout 0, foreign_keys 0), job lacks `max_instances`/`coalesce`, and `_run_check` raises `AttributeError` on the missing trip.

- [ ] **Step 3: Add SQLite timeout + PRAGMA listener**

Replace `backend/app/database.py` engine setup:
```python
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
```

- [ ] **Step 4: Bound the scheduled job**

In `backend/app/agent/scheduler.py`, update `set_interval_hours`:
```python
def set_interval_hours(hours: float):
    """hours <= 0 disables the recurring job."""
    existing = scheduler.get_job(JOB_ID)
    if existing:
        existing.remove()
    if hours and hours > 0:
        scheduler.add_job(
            jobs.run_all_saved_trips, "interval", hours=hours, id=JOB_ID,
            name=f"Re-check all saved trips every {hours:g} h",
            max_instances=1, coalesce=True, misfire_grace_time=300,
        )
```

- [ ] **Step 5: Add the worker semaphore and None-guards to jobs.py**

In `backend/app/agent/jobs.py`, add the semaphore near the top (after the imports / `CONNECTOR_PIPELINE`):
```python
# Cap concurrent condition-check workers so a "run all" or short schedule can't
# spawn unbounded threads all hammering SQLite at once.
MAX_CONCURRENT_CHECKS = 3
_worker_semaphore = threading.BoundedSemaphore(MAX_CONCURRENT_CHECKS)
```

Wrap the worker body so it acquires a slot, and guard the missing check/trip. Replace the start of `_run_check`:
```python
def _run_check(check_id: int):
    with _worker_semaphore:
        _run_check_inner(check_id)


def _run_check_inner(check_id: int):
    db = SessionLocal()
    try:
        check = db.get(models.ConditionCheck, check_id)
        if check is None:
            return  # check row is gone (deleted/race) — nothing to do
        trip = db.get(models.Trip, check.trip_id)
        if trip is None:
            check.status = "failed"
            check.completed_at = dt.datetime.now(dt.timezone.utc)
            check.overall_concern_status = "Source check failed"
            check.summary_text = "Trip was deleted before the condition check could run."
            db.commit()
            return
        settings = get_settings(db)
        enabled = settings.get("connectors_enabled", {})
        # ... rest of the existing body is UNCHANGED from here down ...
```
Everything from `api_keys = {name: get_api_key(...)}` through the `finally: db.close()` stays exactly as it is — only the function was renamed to `_run_check_inner`, the two guards were added, and `settings`/`enabled` lines kept in place.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python -m pytest tests/test_concurrency.py -v
```
Expected: PASS — PRAGMAs set, job bounded, missing-trip check marked `failed`, missing-check call is a quiet no-op.

- [ ] **Step 7: Run the full suite**

```bash
python -m pytest tests/ -q
```
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/database.py backend/app/agent/scheduler.py backend/app/agent/jobs.py backend/tests/test_concurrency.py
git commit -m "fix(concurrency): SQLite busy_timeout+WAL+FK, bounded scheduler job and worker pool, _run_check guards"
```

---

## Task 3: Risk-engine completeness over enabled connectors (Batch 3)

**Bug:** completeness is computed over *all* outputs (`ran = [o for o in outputs]`), counting user-disabled/skipped connectors as 0 in the denominator and ignoring the `enabled` argument — so disabling an optional connector wrongly drops the score below 0.7 and flips overall status to "Data incomplete."

**Files:**
- Modify: `backend/app/services/risk_engine.py:73-77`
- Test: `backend/tests/test_risk_completeness.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_risk_completeness.py`:
```python
"""Completeness must ignore connectors the user disabled."""
from app.schemas import ConnectorOutput
from app.services import risk_engine

SETTINGS = {"fire_radius_miles": 30, "aqi_moderate_threshold": 101,
            "aqi_major_threshold": 151, "wind_gust_moderate_mph": 30,
            "wind_gust_major_mph": 50, "precip_prob_moderate": 60,
            "cold_low_f": 10, "stale_hours": 24}


def _two_good_and_one_disabled():
    return [
        ConnectorOutput(connector_name="nws_weather", status="success", source_name="NWS"),
        ConnectorOutput(connector_name="usgs_elevation", status="success", source_name="USGS"),
        ConnectorOutput(connector_name="airnow", status="skipped",
                        source_name="AirNow", error_message="Disabled in settings"),
    ]


def test_disabled_connector_excluded_from_completeness():
    enabled = {"airnow": False}  # user turned AirNow off
    _flags, _overall, completeness = risk_engine.evaluate(
        _two_good_and_one_disabled(), SETTINGS, "general", enabled)
    # Only the two enabled, successful connectors count -> 2/2 = 1.0
    assert completeness == 1.0


def test_enabled_failure_lowers_completeness():
    outputs = [
        ConnectorOutput(connector_name="nws_weather", status="success"),
        ConnectorOutput(connector_name="usgs_elevation", status="failed",
                        error_message="boom"),
    ]
    _flags, _overall, completeness = risk_engine.evaluate(
        outputs, SETTINGS, "general", {})
    # success(1) + failed(0) over 2 enabled -> 0.5
    assert completeness == 0.5
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_risk_completeness.py -v
```
Expected: FAIL — `test_disabled_connector_excluded_from_completeness` gets `0.67` (3 in denominator), not `1.0`.

- [ ] **Step 3: Compute completeness over enabled connectors only**

In `backend/app/services/risk_engine.py`, replace the completeness block:
```python
    # Completeness: score connectors the user left ENABLED. success=1, partial=0.5,
    # everything else (failed, skipped-for-missing-key) = 0. Connectors the user
    # disabled are excluded entirely so turning one off can't fake "Data incomplete".
    considered = [o for o in outputs if enabled.get(o.connector_name, True)]
    score_points = sum(1.0 if o.status == "success" else 0.5 if o.status == "partial" else 0.0
                       for o in considered)
    completeness = round(score_points / len(considered), 2) if considered else 0.0
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python -m pytest tests/test_risk_completeness.py -v
```
Expected: PASS — `1.0` and `0.5` respectively.

- [ ] **Step 5: Run the full suite**

```bash
python -m pytest tests/ -q
```
Expected: all PASS (existing `test_risk_engine_and_status_language` only asserts `0 <= completeness <= 1`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/risk_engine.py backend/tests/test_risk_completeness.py
git commit -m "fix(risk): compute data completeness over enabled connectors only"
```

---

## Task 4: Report generation robustness (Batch 4)

**Bugs:** weather-period rows subscript dict keys directly (`p['temperature_f']`) → `KeyError` crashes the whole report on partial NWS data; elevation-band rows subscript keys and force-format `temp_offset_f` → `KeyError`/`TypeError`; `print_report` never 404s a bad `check_id`; `min_elevation_ft or '?'` shows `?` for a legitimate 0 ft.

**Files:**
- Modify: `backend/app/services/report_generator.py:67-69,115-118,132-134`
- Modify: `backend/app/routes/trips.py:147-162`
- Test: `backend/tests/test_report_robustness.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_report_robustness.py`:
```python
"""The report must render on partial/missing connector data without crashing,
and print_report must 404 a bad check id."""
import json
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "report.db"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402
from app.services import report_generator  # noqa: E402

_cm = TestClient(app)
client = _cm.__enter__()


def teardown_module(_m):
    _cm.__exit__(None, None, None)


def test_report_survives_partial_weather_and_bands():
    trip = models.Trip(name="Partial", latitude=46.0, longitude=-121.0,
                       start_date="2026-07-01", end_date="2026-07-03")
    check = models.ConditionCheck(trip_id=1, status="complete",
                                  overall_concern_status="No major concerns found",
                                  data_completeness_score=0.8, summary_text="")
    # Weather period missing temperature_f / precip_chance; band missing temp_offset_f.
    check.connector_results = [
        models.ConnectorResult(
            connector_name="nws_weather", status="partial",
            normalized_json=json.dumps({"periods": [{"name": "Tonight"}]})),
        models.ConnectorResult(
            connector_name="elevation_adjusted", status="partial",
            normalized_json=json.dumps({"bands": [{"label": "Summit", "elevation_ft": 14000}]})),
    ]
    check.risk_flags = []
    html = report_generator.generate_report_html(trip, check)  # must not raise
    assert "SummitSignal planning report" in html


def test_report_zero_elevation_not_shown_as_question_mark():
    trip = models.Trip(name="Sea", latitude=36.0, longitude=-121.9,
                       start_date="2026-07-01", end_date="2026-07-03")
    trip.gpx_route = models.GpxRoute(filename="coast.gpx", length_miles=5.0,
                                     min_elevation_ft=0, max_elevation_ft=120)
    html = report_generator.generate_report_html(trip, None)
    assert "0–120 ft" in html  # 0 ft renders as 0, not '?'


def test_print_report_bad_check_id_returns_404():
    trips = client.get("/trips").json()
    r = client.get(f"/trips/{trips[0]['id']}/print-report?check_id=999999")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_report_robustness.py -v
```
Expected: FAIL — first test raises `KeyError: 'temperature_f'`; second shows `?–120`; third returns 200 instead of 404.

- [ ] **Step 3: Make weather-period rendering defensive**

In `backend/app/services/report_generator.py`, replace the period loop (around line 115):
```python
        for p in wx["periods"][:14]:
            parts.append(
                f"<tr><td>{_e(p.get('name', ''))}</td>"
                f"<td>{_e(p.get('temperature_f', '?'))}F</td>"
                f"<td>{_e(p.get('wind_speed', '—'))}</td>"
                f"<td>{_e(p.get('precip_chance', '—'))}%</td>"
                f"<td>{_e(p.get('short_forecast', ''))}</td></tr>")
```

- [ ] **Step 4: Make elevation-band rendering defensive**

Replace the band loop (around line 132):
```python
        for b in adj["bands"]:
            off = b.get("temp_offset_f")
            off_str = "?" if off is None else f"{off:+.0f}"
            parts.append(f"<li>{_e(b.get('label', ''))} ({b.get('elevation_ft', '?')} ft): about "
                         f"{off_str}F vs. the forecast point (estimate).</li>")
```

- [ ] **Step 5: Render a legitimate 0 ft instead of `?`**

Replace the `route_line` (around line 67):
```python
    if gpx:
        length = gpx.length_miles if gpx.length_miles is not None else "?"
        lo = gpx.min_elevation_ft if gpx.min_elevation_ft is not None else "?"
        hi = gpx.max_elevation_ft if gpx.max_elevation_ft is not None else "?"
        route_line = (f"<tr><th>Route (GPX)</th><td>{_e(gpx.filename)} — "
                      f"~{length} mi, {lo}–{hi} ft</td></tr>")
```

- [ ] **Step 6: 404 a bad check_id in print_report**

In `backend/app/routes/trips.py`, update `print_report`:
```python
    if check_id:
        check = db.get(models.ConditionCheck, check_id)
        if check is None:
            raise HTTPException(404, "Condition check not found")
    else:
        check = (db.query(models.ConditionCheck)
                 .filter_by(trip_id=trip_id, status="complete")
                 .order_by(models.ConditionCheck.completed_at.desc()).first())
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
python -m pytest tests/test_report_robustness.py -v
```
Expected: PASS on all three.

- [ ] **Step 8: Run the full suite**

```bash
python -m pytest tests/ -q
```
Expected: all PASS (existing `test_print_report_route` still gets 200 for the no-arg call).

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/report_generator.py backend/app/routes/trips.py backend/tests/test_report_robustness.py
git commit -m "fix(report): defensive rendering on partial data, 0 ft handling, 404 on bad check_id"
```

---

## Task 5: Route & settings correctness (Batch 5)

**Bugs:** `update_trip`'s `if v is not None` guard makes optional fields impossible to clear; `get_settings` overwrites a dict default with a raw string when a stored value fails to parse, breaking downstream `.get()` calls.

**Files:**
- Modify: `backend/app/routes/trips.py:80-88`
- Modify: `backend/app/services/settings_service.py:43-51`
- Test: `backend/tests/test_routes_settings.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_routes_settings.py`:
```python
"""update_trip must be able to clear optional fields; get_settings must keep
the typed default when a stored value is unparseable."""
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "rs.db"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402
from app.services.settings_service import get_settings  # noqa: E402

_cm = TestClient(app)
client = _cm.__enter__()


def teardown_module(_m):
    _cm.__exit__(None, None, None)


def test_update_trip_can_clear_elevation_bands():
    r = client.post("/trips", json={
        "name": "Clearable", "latitude": 47.0, "longitude": -121.0,
        "start_date": "2026-07-01", "end_date": "2026-07-03",
        "elevation_bands": {"trailhead_ft": 1000, "mid_ft": 3000, "high_ft": 6000}})
    tid = r.json()["id"]
    assert r.json()["elevation_bands"] is not None
    r2 = client.patch(f"/trips/{tid}", json={"elevation_bands": None})
    assert r2.status_code == 200
    assert r2.json()["elevation_bands"] is None


def test_get_settings_keeps_default_on_unparseable_value(session):
    session.add(models.AppSetting(key="connectors_enabled", value="not-json{"))
    session.commit()
    out = get_settings(session)
    # Falls back to the default dict, not the raw string.
    assert isinstance(out["connectors_enabled"], dict)
    assert out["connectors_enabled"].get("nws_weather") is True
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_routes_settings.py -v
```
Expected: FAIL — `elevation_bands` stays non-null after the clear, and `get_settings` returns the raw string (so `.get` raises `AttributeError`).

- [ ] **Step 3: Let `update_trip` clear fields**

In `backend/app/routes/trips.py`, update the loop:
```python
    data = body.model_dump(exclude_unset=True)
    if "elevation_bands" in data and data["elevation_bands"] is not None:
        data["elevation_bands"] = json.dumps(data["elevation_bands"])
    for k, v in data.items():
        setattr(trip, k, v)  # exclude_unset already filtered to provided fields
    db.commit()
    db.refresh(trip)
    return _trip_out(trip)
```

- [ ] **Step 4: Keep the default in `get_settings` on parse failure**

In `backend/app/services/settings_service.py`, update the loop:
```python
def get_settings(db: Session) -> dict:
    out = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy
    for row in db.query(models.AppSetting).all():
        if row.key in out:
            try:
                out[row.key] = json.loads(row.value)
            except (json.JSONDecodeError, TypeError):
                continue  # unparseable — keep the typed default rather than a raw string
    return out
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_routes_settings.py -v
```
Expected: PASS — bands clear to null; settings keep the default dict.

- [ ] **Step 6: Run the full suite**

```bash
python -m pytest tests/ -q
```
Expected: all PASS (existing `test_settings_roundtrip` and CRUD tests unaffected).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/trips.py backend/app/services/settings_service.py backend/tests/test_routes_settings.py
git commit -m "fix(routes/settings): allow clearing optional trip fields; keep typed default on bad setting value"
```

---

## Task 6: Connector correctness (Batch 6)

**Bugs:** `elevation_adjusted` uses truthiness checks (`if not target`, `if high and ...`, `any(bands.get(k) ...)`) that silently drop bands at 0 ft or below sea level; `usgs_elevation` reports an Open-Meteo fallback failure with the EPQS source label.

**Files:**
- Modify: `backend/app/connectors/elevation_adjusted.py:31,43,61-62`
- Modify: `backend/app/connectors/usgs_elevation.py:16-63`
- Test: `backend/tests/test_connectors.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_connectors.py`:
```python
"""Connector edge cases: zero/negative elevation bands are kept; a fallback
failure in usgs_elevation is labeled as the fallback source, not EPQS."""
from app.connectors.base import ConnectorContext
from app.connectors import elevation_adjusted, usgs_elevation


def _ctx_with_band(trailhead_ft):
    ctx = ConnectorContext(
        latitude=36.0, longitude=-121.0, start_date="2026-07-01", end_date="2026-07-03",
        elevation_bands={"trailhead_ft": trailhead_ft},
        shared={"nws_normalized": {"periods": [{"name": "Today", "temperature_f": 70}]}})
    ctx.elevation_ft = 50.0
    return ctx


def test_zero_elevation_band_is_kept():
    out = elevation_adjusted.run(_ctx_with_band(0))
    labels = [b["label"] for b in out.normalized["bands"]]
    assert "Trailhead" in labels  # 0 ft must not be dropped


def test_negative_elevation_band_is_kept():
    out = elevation_adjusted.run(_ctx_with_band(-282))  # Badwater Basin
    labels = [b["label"] for b in out.normalized["bands"]]
    assert "Trailhead" in labels


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """EPQS call raises; the Open-Meteo fallback returns no elevation."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None):
        if "epqs" in url:
            raise RuntimeError("EPQS down")
        return _FakeResp({"elevation": []})  # fallback returns nothing


def test_fallback_failure_is_labeled_as_fallback(monkeypatch):
    monkeypatch.setattr(usgs_elevation, "http_client", lambda: _FakeClient())
    ctx = ConnectorContext(latitude=46.0, longitude=-121.0,
                           start_date="2026-07-01", end_date="2026-07-03")
    out = usgs_elevation.run(ctx)
    assert out.status == "failed"
    assert "Open-Meteo" in out.source_name  # not mislabeled as USGS EPQS
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/test_connectors.py -v
```
Expected: FAIL — zero/negative bands are dropped (empty `bands`), and the fallback failure is labeled `"USGS Elevation Point Query Service"`.

- [ ] **Step 3: Use explicit None checks in elevation_adjusted**

In `backend/app/connectors/elevation_adjusted.py`, fix the default-band guard (around line 31):
```python
    gpx = ctx.shared.get("gpx_meta") or {}
    if not any(bands.get(k) is not None for k in ("trailhead_ft", "mid_ft", "high_ft")):
        if gpx.get("min_elevation_ft") is not None and gpx.get("max_elevation_ft") is not None:
            bands = {
                "trailhead_ft": gpx["min_elevation_ft"],
                "mid_ft": (gpx["min_elevation_ft"] + gpx["max_elevation_ft"]) / 2,
                "high_ft": gpx["max_elevation_ft"],
            }
```

Fix the per-band guard (around line 43):
```python
        target = bands.get(key)
        if target is None:
            continue
```

Fix the freezing-band guard (around line 61):
```python
    freezing_band_note = None
    high = bands.get("high_ft")
    if high is not None and nws.get("low_f") is not None:
```

- [ ] **Step 4: Track and report the attempted source in usgs_elevation**

In `backend/app/connectors/usgs_elevation.py`, the failure label already uses local `source_name`/`source_url` variables — make the final `failed(...)` calls report them instead of the hardcoded EPQS values. Replace the function body from the `if meters is None:` (after fallback) and the outer `except`:
```python
            if meters is None:
                return failed(NAME, source_name, source_url, "No elevation value returned")

            feet = meters * 3.28084
            ctx.elevation_ft = feet  # share with elevation-adjusted module
            return ConnectorOutput(
                connector_name=NAME,
                status="success",
                source_name=source_name,
                source_url=source_url,
                source_timestamp=utcnow_iso(),
                raw=raw,
                normalized={"elevation_m": round(meters, 1), "elevation_ft": round(feet, 0)},
            )
    except Exception as e:  # noqa: BLE001
        return failed(NAME, source_name, source_url, str(e))
```
> `source_name`/`source_url` are already initialized to the EPQS values and reassigned to the Open-Meteo values when the fallback is taken, so on a fallback failure they now correctly carry the fallback label. (No new variables needed.)

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python -m pytest tests/test_connectors.py -v
```
Expected: PASS — zero and negative bands kept; fallback failure labeled `"Open-Meteo …"`.

- [ ] **Step 6: Run the full suite**

```bash
python -m pytest tests/ -q
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/connectors/elevation_adjusted.py backend/app/connectors/usgs_elevation.py backend/tests/test_connectors.py
git commit -m "fix(connectors): keep 0/negative elevation bands; label usgs fallback failures correctly"
```

---

## Task 7: Frontend state management (Batch 7)

**Bugs:** switching from a polling trip to a non-running trip leaks the interval and overwrites the dashboard with the old trip's data; `running`/`liveStatus` aren't reset on switch (phantom progress bar); `loadLatestCheck` is memoized with `[]` and captures a stale `beginPolling`/`refreshTrips`; `onTripUpdated` doesn't sync `selectedTrip`; deleting the selected trip leaves a stale selected-point marker; `elevation_m` renders `NaN`; TripDetail GPX line shows `undefined mi` / `…–0 ft`; SearchBar uses index keys.

The frontend has no automated test harness. Verification is by documented manual repro (Step 7); an optional Vitest task is listed at the end.

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/ConditionDashboard.tsx:49`
- Modify: `frontend/src/components/TripDetail.tsx:85-87`
- Modify: `frontend/src/components/SearchBar.tsx:46-48`

- [ ] **Step 1: Add a `stopPolling` helper and use it everywhere the interval is touched**

In `frontend/src/App.tsx`, add a helper just above `beginPolling` (around line 119):
```tsx
  function stopPolling() {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }
```
Then in `beginPolling`, replace the two inline `if (pollRef.current) window.clearInterval(...)` clears with `stopPolling();`:
```tsx
  function beginPolling(checkId: number, trip: Trip) {
    setRunning(true);
    setLiveStatus(null);
    stopPolling();
    pollRef.current = window.setInterval(async () => {
      try {
        const st = await api.getCheckStatus(checkId);
        setLiveStatus(st);
        if (st.status !== "running") {
          stopPolling();
          setRunning(false);
          setCheck(await api.getCheck(checkId));
          refreshTrips();
          if (st.status === "failed") setDashError("Condition check failed. See connector results for details.");
        }
      } catch (e) {
        stopPolling();
        setRunning(false);
        setDashError((e as Error).message);
      }
    }, 1200);
  }
  useEffect(() => () => stopPolling(), []);
```

- [ ] **Step 2: Reset polling/live state at the start of `loadLatestCheck` and drop the stale `useCallback`**

Replace `loadLatestCheck` (lines 92-109). Convert it from `useCallback(..., [])` to a plain async function so it always closes over the current `beginPolling`/`refreshTrips`, and unconditionally stop any active poll + reset live state first:
```tsx
  // ---- load latest check when trip selected ----
  async function loadLatestCheck(trip: Trip) {
    stopPolling();
    setRunning(false);
    setLiveStatus(null);
    setCheck(null);
    setDashError(null);
    setLoadingCheck(true);
    try {
      const list = await api.listChecks(trip.id);
      const latest = list.find((c) => c.status === "complete");
      const runningOne = list.find((c) => c.status === "running");
      if (runningOne) {
        beginPolling(runningOne.id, trip);
      }
      if (latest) setCheck(await api.getCheck(latest.id));
    } catch (e) {
      setDashError((e as Error).message);
    } finally {
      setLoadingCheck(false);
    }
  }
```
Remove `useCallback` from the import on line 1 if it is no longer used anywhere else in the file. Check first:
- If `useCallback` is still used by `refreshTrips`, leave the import. (It is — `refreshTrips` on line 65 uses it, so keep the import.)

- [ ] **Step 3: Sync `selectedTrip` in `onTripUpdated` and clear the marker in `onTripDeleted`**

In the `TripDetail` props (around lines 238-246), update both callbacks:
```tsx
            onTripUpdated={(t) => {
              setDetailTrip(t);
              setTrips((prev) => prev.map((x) => (x.id === t.id ? t : x)));
              setSelectedTrip((prev) => (prev && prev.id === t.id ? t : prev));
            }}
            onTripDeleted={(id) => {
              setTrips((prev) => prev.filter((x) => x.id !== id));
              if (selectedTrip?.id === id) {
                setSelectedTrip(null);
                setCheck(null);
                setSelectedPoint(null);
                setPointName(null);
              }
              setView("dashboard");
            }}
```

- [ ] **Step 4: Guard `elevation_m` in ConditionDashboard**

In `frontend/src/components/ConditionDashboard.tsx`, line 49, guard the metres value:
```tsx
            <span className="v">{Math.round(n.elevation_ft).toLocaleString()} ft{n.elevation_m != null ? ` (${Math.round(n.elevation_m)} m)` : ""}{n.fallback_source ? ` · via ${n.fallback_source}` : ""}</span>
```

- [ ] **Step 5: Guard the GPX summary line in TripDetail**

In `frontend/src/components/TripDetail.tsx`, lines 83-89, guard both numbers:
```tsx
          {trip.gpx_route && (
            <span>
              GPX: {trip.gpx_route.length_miles != null ? `${trip.gpx_route.length_miles.toFixed(1)} mi` : "—"}
              {trip.gpx_route.min_elevation_ft != null && trip.gpx_route.max_elevation_ft != null &&
                `, ${Math.round(trip.gpx_route.min_elevation_ft).toLocaleString()}–${Math.round(trip.gpx_route.max_elevation_ft).toLocaleString()} ft`}
            </span>
          )}
```

- [ ] **Step 6: Use a stable key in SearchBar**

In `frontend/src/components/SearchBar.tsx`, line 48, replace the index key:
```tsx
          {results.map((r, i) => (
            <div
              key={`${r.latitude},${r.longitude},${r.display_name}`}
              className="res"
              onClick={() => { onResult(r); setResults([]); setQuery(""); }}
            >
```
(Keep `(r, i)` in the map signature only if `i` is still referenced; if not, change to `(r) =>`.)

- [ ] **Step 7: Typecheck/build and manually verify**

Run from `frontend/`:
```bash
npm run build
```
Expected: TypeScript compiles with no errors.

Then run both servers (`uvicorn app.main:app --reload --port 8000` in `backend/`, `npm run dev` in `frontend/`) and confirm:
1. **Polling leak:** start a condition check on trip A; while it runs, select trip B (which has no running check). The dashboard shows trip B with no phantom "in progress" bar, and when A finishes the dashboard does **not** flip to A's data.
2. **Notes sync:** open a GPX trip's detail, edit and save notes; the GPX route still shows on the map and the detail header still shows the GPX line.
3. **Delete:** delete the currently selected trip; the orange selected-point marker disappears and the coordinate readout clears.
4. **Renders:** a connector result missing `elevation_m` shows `… ft` with no `(NaN m)`; a GPX trip with no max elevation shows `—`/clean text, never `undefined mi` or `…–0 ft`.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/ConditionDashboard.tsx frontend/src/components/TripDetail.tsx frontend/src/components/SearchBar.tsx
git commit -m "fix(frontend): stop polling on trip-switch, reset live state, sync selection, guard renders"
```

- [ ] **Step 9 (OPTIONAL): Add a Vitest regression test for the polling leak**

Only do this if adding a frontend test toolchain is acceptable. Install dev deps in `frontend/`:
```bash
npm install -D vitest @testing-library/react @testing-library/jsdom jsdom
```
Add to `frontend/vite.config.ts` a `test: { environment: "jsdom" }` block, then write a test that mounts `App`, mocks `api`, starts a check on trip A, switches to trip B, resolves A's poll, and asserts the dashboard still reflects B. If the toolchain add is not wanted, skip this step — the manual repro in Step 7 is the verification of record. Document the choice in the commit message.

---

## Self-Review

**Spec coverage** (every spec batch maps to a task):
- Batch 1 (persistence/cascade) → Task 1 ✓
- Batch 2 (concurrency hardening) → Task 2 ✓ (busy_timeout+WAL+FK, bounded scheduler, worker semaphore, None-guards)
- Batch 3 (risk-engine completeness) → Task 3 ✓
- Batch 4 (report robustness) → Task 4 ✓ (weather, bands, 0 ft, 404)
- Batch 5 (route/settings) → Task 5 ✓ (clearable fields, settings default)
- Batch 6 (connectors) → Task 6 ✓ (elevation bands, usgs label)
- Batch 7 (frontend state) → Task 7 ✓ (polling leak, reset, stale closure, selection sync, marker, renders, keys)
- Spec note on FK-enforcement/cascade coupling → handled: Task 1 cascade works at the ORM layer independent of Task 2's PRAGMA, and Task 2 adds `foreign_keys=ON` as belt-and-braces. Tasks 1 and 2 may land in either order.

**Note on a spec item refined during planning:** the spec's "notes-save may drop `gpx_route`" concern was found safe — `_trip_out` (trips.py:18-39) fully hydrates `gpx_route` and `update_trip` returns it. The real residual (un-synced `selectedTrip`) is fixed in Task 7 Step 3 instead.

**Placeholder scan:** no TBD/TODO; every code step shows complete code; the only "optional" item (Task 7 Step 9) is explicitly optional with manual verification as the default.

**Type/name consistency:** `_run_check` (wrapper) / `_run_check_inner` (body) named consistently across Task 2; `stopPolling` defined once and reused in `beginPolling`, `loadLatestCheck`, and the unmount effect; `considered` used consistently in Task 3; `source_name`/`source_url` reused (not renamed) in Task 6.

**Existing-data caveat (carry into execution):** enabling `PRAGMA foreign_keys=ON` (Task 2) on a pre-existing `summit_signal.db` that already contains orphaned rows is harmless for new operations but means a one-time stale DB is fine to delete in dev. WAL mode adds `-wal`/`-shm` sidecar files (already gitignored in Task 0).
