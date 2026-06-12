# Multi-User Hosted Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn SummitSignal into a small multi-user web app (Vercel frontend + Render backend + Neon Postgres) where the map is publicly browsable but trips, checks, and settings are private per account, logging in with self-hosted email/password.

**Architecture:** Keep the existing FastAPI + SQLAlchemy backend and React/Vite frontend. Add a `users` table, JWT bearer auth, and a `user_id` owner on trips so all per-user data is scoped through the trip graph. Make the DB selectable via `DATABASE_URL` (SQLite local, Postgres prod). Remove the scheduler and Ollama. The frontend gains an auth context that gates trip/dashboard/settings panels while leaving the map public.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2.x, passlib[bcrypt], pyjwt, psycopg (Postgres driver), pytest; React 18, TypeScript, Vite, MapLibre GL.

**Reference spec:** `docs/superpowers/specs/2026-06-12-multi-user-hosted-deployment-design.md`

**Conventions:**
- Backend commands run from `backend/` using the project venv: `.venv/Scripts/python -m pytest tests/ -q`.
- Frontend commands run from `frontend/`: `npm run build`.
- Commit after each task: `feat(area): summary` / `chore(area): summary`.
- This plan is staged. Each stage ends with the full suite green (backend) or a clean build (frontend).

---

## File Structure

**Backend, created:**
- `backend/app/security.py` — password hashing, JWT encode/decode, `get_current_user` dependencies.
- `backend/app/routes/auth.py` — `/auth/signup`, `/auth/login`, `/auth/me`.
- `backend/app/seed.py` — `SEED_TRIPS` data + `seed_for_user(db, user_id)`.
- `backend/tests/test_auth.py`, `test_isolation.py`, `test_settings_per_user.py`.

**Backend, modified:**
- `backend/app/database.py` — `DATABASE_URL` selection; SQLite-only pragmas/connect_args.
- `backend/app/models.py` — `User`; `Trip.user_id`; `AppSetting` composite PK; remove `ApiKey`.
- `backend/app/schemas.py` — auth schemas; drop Ollama/schedule/api_keys from settings schemas.
- `backend/app/services/settings_service.py` — per-user settings; env-only API keys; drop Ollama/schedule defaults.
- `backend/app/agent/summarizer.py` — rule-based only (drop Ollama branch/import).
- `backend/app/agent/jobs.py` — load settings by the trip's owner; scope `run_all_saved_trips`.
- `backend/app/routes/trips.py`, `checks.py`, `misc.py` — auth + ownership scoping; public search/health.
- `backend/app/main.py` — env CORS; remove scheduler/seed/Ollama startup; include auth router.
- `backend/requirements.txt` — add `psycopg[binary]`, `passlib[bcrypt]`, `pyjwt`.
- `backend/tests/conftest.py` — set test `SIGNUP_CODE`; add `signup_and_token` helper.

**Backend, removed:**
- `backend/app/agent/scheduler.py`, `backend/app/agent/ollama_client.py`.

**Frontend, created:**
- `frontend/src/lib/auth.tsx` — `AuthProvider` + `useAuth` (token storage, current user).
- `frontend/src/components/AuthScreen.tsx` — login/signup form.

**Frontend, modified:**
- `frontend/src/lib/api.ts` — `VITE_API_BASE`; attach `Authorization`; auth endpoints; drop `ollamaModels`.
- `frontend/src/types.ts` — `User`; drop Ollama/schedule/api_keys-write fields.
- `frontend/src/App.tsx` — auth gating of panels; header login/logout; pass-through stays.
- `frontend/src/components/ConditionDashboard.tsx` — 12h staleness nudge.
- `frontend/src/components/SavedTrips.tsx` — stale indicator dot.
- `frontend/src/components/SettingsView.tsx` — remove API-key + Ollama/schedule sections.
- `frontend/src/main.tsx` — wrap `App` in `AuthProvider`.

**Deploy, created:**
- `backend/render.yaml`, `frontend/vercel.json`, `.env.example`, README updates.

---

# STAGE 1 — DB portability + teardown (scheduler, Ollama)

## Task 1: DATABASE_URL-aware engine with SQLite-only pragmas

**Files:**
- Modify: `backend/app/database.py`
- Test: `backend/tests/test_db_portability.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_db_portability.py`:
```python
"""The engine must read DATABASE_URL and only apply SQLite-specific setup on SQLite."""
import importlib


def test_postgres_url_selected(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    import app.database as database
    importlib.reload(database)
    try:
        assert database.engine.url.get_backend_name() == "postgresql"
        # No SQLite connect_args leaked onto a Postgres engine.
        assert "check_same_thread" not in database.engine.url.query
    finally:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        importlib.reload(database)  # restore default SQLite engine for other tests


def test_sqlite_default_when_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import app.database as database
    importlib.reload(database)
    assert database.engine.url.get_backend_name() == "sqlite"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_db_portability.py -v`
Expected: FAIL — current `database.py` ignores `DATABASE_URL` and always builds a SQLite engine.

- [ ] **Step 3: Implement the portable engine**

Replace the whole of `backend/app/database.py`:
```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_db_portability.py -v`
Expected: PASS (both cases).

- [ ] **Step 5: Run the full suite**

Run: `cd backend && .venv/Scripts/python -m pytest tests/ -q`
Expected: all PASS (existing tests still use the SQLite default).

- [ ] **Step 6: Commit**

```bash
git add backend/app/database.py backend/tests/test_db_portability.py
git commit -m "feat(db): select engine via DATABASE_URL; SQLite-only pragmas/connect_args"
```

## Task 2: Env-driven CORS, and remove scheduler from startup

**Files:**
- Modify: `backend/app/main.py`
- Remove: `backend/app/agent/scheduler.py`
- Test: `backend/tests/test_app.py` (the existing health/CORS behavior must still pass)

- [ ] **Step 1: Delete the scheduler module and its imports**

Delete `backend/app/agent/scheduler.py`.

- [ ] **Step 2: Rewrite `backend/app/main.py`**

Replace the whole file:
```python
"""SummitSignal backend entrypoint.

Run with:  uvicorn app.main:app --reload --port 8000
Creates the schema on startup. There is no global seeding: sample trips are
seeded per user at signup. CORS origins come from ALLOWED_ORIGINS."""
from __future__ import annotations
import datetime as dt
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401 - registers tables
from .database import Base, engine
from .routes import auth as auth_routes
from .routes import trips as trips_routes
from .routes import checks as checks_routes
from .routes import misc as misc_routes

DEFAULT_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def _allowed_origins() -> list[str]:
    raw = os.environ.get("ALLOWED_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or DEFAULT_ORIGINS


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="SummitSignal", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "app": "SummitSignal", "time": dt.datetime.now(dt.timezone.utc)}


app.include_router(auth_routes.router)
app.include_router(trips_routes.router)
app.include_router(checks_routes.router)
app.include_router(misc_routes.router)
```

> Note: `auth_routes` does not exist until Task 6. Until then this import fails. To keep Stage 1 runnable, comment out the `auth` import + `include_router(auth_routes.router)` line now and restore them in Task 6. (The implementer should add a `# TODO(stage2): auth router` only as a temporary scaffold and MUST restore it in Task 6.) Alternatively, do Task 6's file creation first. For a clean sequence, create an empty `backend/app/routes/auth.py` with `from fastapi import APIRouter; router = APIRouter()` now, and flesh it out in Task 6.

Create `backend/app/routes/auth.py` as a stub so the import resolves:
```python
"""Auth routes (filled in Stage 2)."""
from fastapi import APIRouter

router = APIRouter()
```

- [ ] **Step 3: Verify health + CORS still work**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_app.py::test_health -v`
Expected: PASS.

- [ ] **Step 4: Confirm app imports (no scheduler references remain)**

Run: `cd backend && .venv/Scripts/python -c "from app.main import app; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/routes/auth.py
git rm backend/app/agent/scheduler.py
git commit -m "chore(backend): env-driven CORS, remove scheduler, schema-only startup"
```

## Task 3: Remove Ollama from the summarizer

**Files:**
- Modify: `backend/app/agent/summarizer.py`
- Remove: `backend/app/agent/ollama_client.py`
- Test: `backend/tests/test_app.py::test_rule_based_summary_contains_disclaimer` (must still pass)

- [ ] **Step 1: Simplify `summarize` to rule-based only**

In `backend/app/agent/summarizer.py`, remove `from . import ollama_client`, delete `_ollama`, `_truncate`, and `SYSTEM_PROMPT`, and replace `summarize` with:
```python
def summarize(trip: dict, flags: list[dict], outputs: list[dict],
              checklist: list[str], settings: dict) -> tuple[str, str]:
    """Returns (markdown, generator_name). Rule-based only."""
    return _rule_based(trip, flags, outputs, checklist), "rule_based"
```
Leave `_rule_based`, `_section`, and `DISCLAIMER` unchanged. (The `settings` parameter is kept for signature stability with callers; it is unused.)

- [ ] **Step 2: Delete the Ollama client**

Delete `backend/app/agent/ollama_client.py`.

- [ ] **Step 3: Run the summarizer test**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_app.py::test_rule_based_summary_contains_disclaimer -v`
Expected: PASS (it already asserts `gen == "rule_based"`).

- [ ] **Step 4: Confirm no remaining Ollama imports**

Run: `cd backend && .venv/Scripts/python -c "import app.agent.summarizer; print('ok')"`
Expected: `ok` (no ImportError for ollama_client).

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/summarizer.py
git rm backend/app/agent/ollama_client.py
git commit -m "chore(agent): remove Ollama; summaries are rule-based only"
```

## Task 4: Drop Ollama/schedule settings and env-only API keys in settings_service

**Files:**
- Modify: `backend/app/services/settings_service.py`
- Test: existing `backend/tests/test_routes_settings.py::test_get_settings_keeps_default_on_unparseable_value` must keep passing after the signature change in Task 9; for now keep the module importable.

> This task only trims defaults and the API-key path. Per-user scoping (the `user_id` argument) is added in Stage 3 (Task 9), because it depends on the `User` model. To avoid churn, do the trimming now and the scoping in Task 9.

- [ ] **Step 1: Trim `DEFAULT_SETTINGS` and remove the DB API-key path**

In `backend/app/services/settings_service.py`, set `DEFAULT_SETTINGS` to (drop `ollama_*` and `schedule_hours`):
```python
DEFAULT_SETTINGS = {
    "fire_radius_miles": 30.0,
    "aqi_moderate_threshold": 101,
    "aqi_major_threshold": 151,
    "wind_gust_moderate_mph": 30.0,
    "wind_gust_major_mph": 50.0,
    "precip_prob_moderate": 60.0,
    "cold_low_f": 10.0,
    "stale_hours": 24.0,
    "connectors_enabled": {
        "nws_weather": True, "usgs_elevation": True, "elevation_adjusted": True,
        "nasa_firms": True, "nifc_wfigs": True, "airnow": True,
        "nps_alerts": True, "avalanche": True, "weather_discussion": True,
    },
}
```
Keep `ENV_KEY_MAP`, `get_api_key` (env-first; it already returns "" when no row — but we will drop the DB row path), and `api_keys_present`. Replace `get_api_key` and `set_api_key` so keys come from env only:
```python
def get_api_key(db, name: str) -> str:
    """API keys come from environment variables only (operator-provided)."""
    env_var = ENV_KEY_MAP.get(name)
    return os.environ.get(env_var, "").strip() if env_var else ""
```
Delete `set_api_key` entirely (no longer used). `api_keys_present` stays as `{name: bool(get_api_key(db, name)) for name in ENV_KEY_MAP}` (the `db` arg is now unused but kept for call-site stability; it is removed in Task 9).

- [ ] **Step 2: Confirm import + defaults**

Run: `cd backend && .venv/Scripts/python -c "from app.services.settings_service import DEFAULT_SETTINGS; assert 'ollama_enabled' not in DEFAULT_SETTINGS and 'schedule_hours' not in DEFAULT_SETTINGS; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/settings_service.py
git commit -m "chore(settings): drop Ollama/schedule defaults; API keys from env only"
```

## Task 5: Remove Ollama/schedule routes and API-key writing in misc.py; remove ApiKey usage in jobs

**Files:**
- Modify: `backend/app/routes/misc.py`
- Modify: `backend/app/agent/jobs.py`
- Test: `backend/tests/test_concurrency.py` (must still pass), `backend/tests/test_app.py::test_settings_roundtrip` (will be updated in Task 9; for now ensure import works)

- [ ] **Step 1: Remove Ollama/schedule/agent-jobs routes and key writing from `misc.py`**

In `backend/app/routes/misc.py`: delete the `ollama_models` route (`GET /settings/ollama-models`), the `set_schedule` route (`POST /agent/schedule`), the `get_jobs` route (`GET /agent/jobs`), and the `ollama_client`, `scheduler` imports. In `write_settings`, remove the `scheduler.set_interval_hours(...)` block and the `api_keys` handling (keys are env-only now). The trimmed `write_settings` becomes:
```python
@router.post("/settings", response_model=SettingsOut)
def write_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    data.pop("api_keys", None)  # ignored: API keys are env-only now
    s = update_settings(db, data)
    s["api_keys_present"] = api_keys_present(db)
    return SettingsOut(**s)
```
Keep `read_settings`, `search_location`, and `run_all` (the agent run-all route). Remove `set_api_key` from the import list. Remove `ollama_client` from the `from ..agent import ...` import (keep `jobs`).

- [ ] **Step 2: Make jobs use env-only API keys**

In `backend/app/agent/jobs.py`, the line `api_keys = {name: get_api_key(db, name) for name in ("firms", "airnow", "nps")}` still works (get_api_key now ignores db). Leave it. (Per-user settings wiring happens in Task 10.)

- [ ] **Step 3: Confirm imports and concurrency tests**

Run: `cd backend && .venv/Scripts/python -c "from app.main import app; print('ok')"` then `cd backend && .venv/Scripts/python -m pytest tests/test_concurrency.py -q`
Expected: `ok`, then concurrency tests PASS.

- [ ] **Step 4: Update settings tests that referenced removed fields**

In `backend/tests/test_app.py::test_settings_roundtrip`, the body posts `fire_radius_miles` and `api_keys`. API keys are now env-only and ignored. Change the assertion to not require `api_keys_present.airnow is True` from a POSTed key. Replace that test body with:
```python
def test_settings_roundtrip():
    r = client.post("/settings", json={"fire_radius_miles": 45})
    assert r.status_code == 200
    assert r.json()["fire_radius_miles"] == 45
```
(Once Stage 3 adds auth, this test gets an auth header in Task 12; for now it stays unauthenticated and passes.)

- [ ] **Step 5: Run the full suite**

Run: `cd backend && .venv/Scripts/python -m pytest tests/ -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/misc.py backend/tests/test_app.py
git commit -m "chore(routes): remove Ollama/schedule/agent-jobs routes; API keys env-only"
```

---

# STAGE 2 — Auth foundation

## Task 6: User model and auth schemas

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_auth.py` (created in Task 8)

- [ ] **Step 1: Add the `User` model and remove `ApiKey`**

In `backend/app/models.py`, add after `utcnow`:
```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=utcnow)
```
Delete the `ApiKey` class (keys are env-only now). Leave other models for Task 7.

- [ ] **Step 2: Add auth schemas**

In `backend/app/schemas.py`, add near the top (after imports):
```python
# ---------- Auth ----------

class SignupRequest(BaseModel):
    email: str
    password: str
    invite_code: str


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    email: str


class TokenResponse(BaseModel):
    token: str
    user: UserOut
```

- [ ] **Step 3: Confirm models/schemas import**

Run: `cd backend && .venv/Scripts/python -c "from app import models, schemas; assert hasattr(models,'User') and not hasattr(models,'ApiKey'); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py
git commit -m "feat(auth): add User model and auth schemas; remove ApiKey"
```

## Task 7: Security module (hashing, JWT, current-user dependency)

**Files:**
- Create: `backend/app/security.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_auth.py` (Task 8)

- [ ] **Step 1: Add dependencies**

In `backend/requirements.txt`, add:
```
passlib[bcrypt]>=1.7
pyjwt>=2.8
psycopg[binary]>=3.1
```
Then install into the venv:
Run: `cd backend && .venv/Scripts/python -m pip install "passlib[bcrypt]>=1.7" "pyjwt>=2.8" "psycopg[binary]>=3.1"`
Expected: installs succeed.

- [ ] **Step 2: Create `backend/app/security.py`**

```python
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
_DEV_SECRET = "dev-insecure-secret-change-me"

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
```

- [ ] **Step 3: Confirm import**

Run: `cd backend && .venv/Scripts/python -c "from app.security import hash_password, verify_password, create_token; h=hash_password('abc'); assert verify_password('abc',h) and not verify_password('x',h); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt backend/app/security.py
git commit -m "feat(auth): security module (bcrypt hashing, JWT, current-user deps)"
```

## Task 8: Seed module + auth routes (signup/login/me)

**Files:**
- Create: `backend/app/seed.py`
- Modify: `backend/app/routes/auth.py` (replace the stub)
- Modify: `backend/tests/conftest.py` (test SIGNUP_CODE + helper)
- Test: `backend/tests/test_auth.py`

- [ ] **Step 1: Create the seed module**

Move the seed data out of `main.py` into `backend/app/seed.py`:
```python
"""Sample trips seeded into each new account at signup."""
from __future__ import annotations
import datetime as dt

from . import models

SEED_TRIPS = [
    {"name": "Mount Rainier, DC Route", "location_name": "Mount Rainier, WA",
     "latitude": 46.8523, "longitude": -121.7603, "trip_type": "mountaineering",
     "notes": "Sample trip. Paradise to Camp Muir to summit via Disappointment Cleaver.",
     "elevation_bands": '{"trailhead_ft": 5400, "mid_ft": 10080, "high_ft": 14410}'},
    {"name": "Longs Peak, Keyhole", "location_name": "Longs Peak, CO",
     "latitude": 40.2549, "longitude": -105.6160, "trip_type": "mountaineering",
     "notes": "Sample trip.",
     "elevation_bands": '{"trailhead_ft": 9405, "mid_ft": 12000, "high_ft": 14259}'},
    {"name": "Yosemite Valley weekend", "location_name": "Yosemite Valley, CA",
     "latitude": 37.7456, "longitude": -119.5936, "trip_type": "backpacking",
     "notes": "Sample trip.", "elevation_bands": None},
    {"name": "Grand Canyon South Rim", "location_name": "Grand Canyon South Rim, AZ",
     "latitude": 36.0544, "longitude": -112.1401, "trip_type": "general",
     "notes": "Sample trip.", "elevation_bands": None},
]


def seed_for_user(db, user_id: int) -> None:
    today = dt.date.today()
    start = (today + dt.timedelta(days=7)).isoformat()
    end = (today + dt.timedelta(days=9)).isoformat()
    for t in SEED_TRIPS:
        db.add(models.Trip(user_id=user_id, start_date=start, end_date=end, **t))
    db.commit()
```
> `models.Trip` gains `user_id` in Task 9; `seed_for_user` is called from signup, which is exercised after Task 9. Sequence note: do Task 9 before running the auth tests that assert seeded trips. The signup route is written here but its seeding assertion test lives in Task 9's suite run.

- [ ] **Step 2: Replace `backend/app/routes/auth.py`**

```python
"""Authentication: signup (invite-gated), login, current user."""
from __future__ import annotations
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
    if body.invite_code != os.environ.get("SIGNUP_CODE", ""):
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
```

- [ ] **Step 3: Add test SIGNUP_CODE and a shared helper to conftest**

In `backend/tests/conftest.py`, after the existing temp-DB line, add:
```python
os.environ.setdefault("SIGNUP_CODE", "test-invite-code")
```
And append a helper at the end of the file:
```python
def signup_and_token(client, email="user@example.com", password="password123"):
    """Sign up a fresh user via the API and return (token, user_id, headers)."""
    r = client.post("/auth/signup", json={
        "email": email, "password": password, "invite_code": os.environ["SIGNUP_CODE"]})
    assert r.status_code == 200, r.text
    body = r.json()
    headers = {"Authorization": f"Bearer {body['token']}"}
    return body["token"], body["user"]["id"], headers
```

- [ ] **Step 4: Restore the auth router import in `main.py`**

If Task 2 left the `auth` import/`include_router` commented, uncomment them now so `/auth/*` is mounted. (If you created the stub router, the import already resolves; the routes are now real.)

- [ ] **Step 5: Write `backend/tests/test_auth.py`**

```python
"""Auth: invite-gated signup, login, token validation."""
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "auth.db"))
os.environ.setdefault("SIGNUP_CODE", "test-invite-code")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

_cm = TestClient(app)
client = _cm.__enter__()


def teardown_module(_m):
    _cm.__exit__(None, None, None)


def test_signup_requires_invite_code():
    r = client.post("/auth/signup", json={"email": "a@b.com", "password": "password123",
                                          "invite_code": "wrong"})
    assert r.status_code == 400


def test_signup_then_login_and_me():
    r = client.post("/auth/signup", json={"email": "Alice@Example.com", "password": "password123",
                                          "invite_code": os.environ["SIGNUP_CODE"]})
    assert r.status_code == 200
    token = r.json()["token"]
    assert r.json()["user"]["email"] == "alice@example.com"  # normalized

    r2 = client.post("/auth/login", json={"email": "alice@example.com", "password": "password123"})
    assert r2.status_code == 200 and r2.json()["token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "alice@example.com"


def test_duplicate_email_rejected():
    body = {"email": "dup@example.com", "password": "password123",
            "invite_code": os.environ["SIGNUP_CODE"]}
    assert client.post("/auth/signup", json=body).status_code == 200
    assert client.post("/auth/signup", json=body).status_code == 409


def test_login_wrong_password():
    client.post("/auth/signup", json={"email": "bob@example.com", "password": "password123",
                                      "invite_code": os.environ["SIGNUP_CODE"]})
    r = client.post("/auth/login", json={"email": "bob@example.com", "password": "nope"})
    assert r.status_code == 401


def test_me_requires_valid_token():
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
```

- [ ] **Step 6: Run auth tests**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_auth.py -v`
Expected: these PASS only after Task 9 adds `Trip.user_id` (signup seeds trips). If running before Task 9, signup raises on the unknown `user_id` kwarg. **Run this step's verification at the end of Task 9.** For now, just confirm the app imports: `cd backend && .venv/Scripts/python -c "from app.main import app; print('ok')"` → `ok`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/seed.py backend/app/routes/auth.py backend/tests/conftest.py backend/tests/test_auth.py
git commit -m "feat(auth): signup/login/me routes, per-user seed module, test helper"
```

---

# STAGE 3 — Per-user data + settings

## Task 9: Add Trip.user_id, per-user settings PK, scope settings_service

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/services/settings_service.py`
- Test: `backend/tests/test_settings_per_user.py`, plus the deferred Task 8 auth run.

- [ ] **Step 1: Add `user_id` to Trip and make AppSetting per-user**

In `backend/app/models.py`:
- Add to `Trip` (after `id`): `user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)`
- Change `AppSetting` to a composite PK:
```python
class AppSetting(Base):
    __tablename__ = "app_settings"
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    key = Column(String, primary_key=True)
    value = Column(Text, default="")
```

- [ ] **Step 2: Scope settings_service by user**

In `backend/app/services/settings_service.py`, change the signatures:
```python
def get_settings(db: Session, user_id: int) -> dict:
    out = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy
    rows = db.query(models.AppSetting).filter(models.AppSetting.user_id == user_id).all()
    for row in rows:
        if row.key in out:
            try:
                out[row.key] = json.loads(row.value)
            except (json.JSONDecodeError, TypeError):
                continue
    return out


def update_settings(db: Session, user_id: int, updates: dict) -> dict:
    for key, value in updates.items():
        if key not in DEFAULT_SETTINGS or value is None:
            continue
        if key == "connectors_enabled":
            current = get_settings(db, user_id)["connectors_enabled"]
            current.update(value)
            value = current
        row = db.get(models.AppSetting, {"user_id": user_id, "key": key})
        if row is None:
            db.add(models.AppSetting(user_id=user_id, key=key, value=json.dumps(value)))
        else:
            row.value = json.dumps(value)
    db.commit()
    return get_settings(db, user_id)
```
`get_api_key(db, name)` and `api_keys_present(db)` keep their `db` param (env-only) — unchanged.

- [ ] **Step 3: Write per-user settings test**

Create `backend/tests/test_settings_per_user.py`:
```python
"""Per-user settings isolation at the service layer."""
from app import models
from app.security import hash_password
from app.services.settings_service import get_settings, update_settings


def _user(session, email):
    u = models.User(email=email, password_hash=hash_password("password123"))
    session.add(u)
    session.commit()
    return u.id


def test_settings_are_per_user(session):
    a = _user(session, "a@x.com")
    b = _user(session, "b@x.com")
    update_settings(session, a, {"fire_radius_miles": 99})
    assert get_settings(session, a)["fire_radius_miles"] == 99
    assert get_settings(session, b)["fire_radius_miles"] == 30.0  # default, unaffected


def test_unparseable_value_keeps_default(session):
    a = _user(session, "c@x.com")
    session.add(models.AppSetting(user_id=a, key="connectors_enabled", value="not-json{"))
    session.commit()
    assert isinstance(get_settings(session, a)["connectors_enabled"], dict)
```

- [ ] **Step 4: Run the per-user settings tests and the deferred auth tests**

Run: `cd backend && .venv/Scripts/python -m pytest tests/test_settings_per_user.py tests/test_auth.py -v`
Expected: all PASS (signup now succeeds because `Trip.user_id` exists, and seeding works).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/services/settings_service.py backend/tests/test_settings_per_user.py
git commit -m "feat(data): Trip.user_id + per-user app_settings; scope settings_service"
```

## Task 10: Scope trip routes + jobs to the owner

**Files:**
- Modify: `backend/app/routes/trips.py`
- Modify: `backend/app/agent/jobs.py`
- Test: `backend/tests/test_isolation.py` (Task 11)

- [ ] **Step 1: Add an ownership helper and auth to every trip route**

In `backend/app/routes/trips.py`, add imports and a helper:
```python
from ..security import get_current_user

def _owned_trip(trip_id: int, user: models.User, db: Session) -> models.Trip:
    trip = db.get(models.Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(404, "Trip not found")
    return trip
```
Then update each route to require `user: models.User = Depends(get_current_user)` and scope by owner:
```python
@router.post("/trips", response_model=TripOut)
def create_trip(body: TripCreate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    trip = models.Trip(
        user_id=user.id,
        name=body.name, location_name=body.location_name,
        latitude=body.latitude, longitude=body.longitude,
        start_date=body.start_date, end_date=body.end_date,
        trip_type=body.trip_type, notes=body.notes,
        elevation_bands=body.elevation_bands.model_dump_json() if body.elevation_bands else None,
    )
    db.add(trip)
    db.add(models.Location(name=body.location_name or body.name,
                           latitude=body.latitude, longitude=body.longitude,
                           kind="trip", source="manual"))
    db.commit()
    db.refresh(trip)
    return _trip_out(trip)


@router.get("/trips", response_model=list[TripOut])
def list_trips(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    trips = (db.query(models.Trip).filter(models.Trip.user_id == user.id)
             .order_by(models.Trip.created_at.desc()).all())
    return [_trip_out(t) for t in trips]


@router.get("/trips/{trip_id}", response_model=TripOut)
def get_trip(trip_id: int, db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)):
    return _trip_out(_owned_trip(trip_id, user, db))
```
Apply the same pattern (add `user: models.User = Depends(get_current_user)` and replace `db.get(models.Trip, trip_id)` + 404 with `_owned_trip(trip_id, user, db)`) to: `update_trip`, `delete_trip`, `upload_gpx`, `run_condition_check`, `list_trip_checks`, and `print_report`. For `print_report`, also scope the `check_id` branch so a check from another user 404s: after fetching the trip via `_owned_trip`, when `check_id` is provided, require `check.trip_id == trip.id` else 404.

- [ ] **Step 2: Make jobs load the trip owner's settings**

In `backend/app/agent/jobs.py`, inside `_run_check_inner`, after the `trip` None-guard, change:
```python
        settings = get_settings(db, trip.user_id)
```
(`get_settings` now requires a user_id; the trip carries it.) `api_keys = {name: get_api_key(db, name) for name in ("firms", "airnow", "nps")}` stays.

- [ ] **Step 3: Confirm import**

Run: `cd backend && .venv/Scripts/python -c "from app.main import app; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routes/trips.py backend/app/agent/jobs.py
git commit -m "feat(trips): require auth, scope all trip/check routes to the owner"
```

## Task 11: Scope check routes + settings routes + agent run-all; public search/health

**Files:**
- Modify: `backend/app/routes/checks.py`
- Modify: `backend/app/routes/misc.py`
- Modify: `backend/app/agent/jobs.py` (run_all_saved_trips by user)
- Test: `backend/tests/test_isolation.py`

- [ ] **Step 1: Scope check routes to the owner**

In `backend/app/routes/checks.py`, add `from ..security import get_current_user` and an owned-check helper:
```python
def _owned_check(check_id: int, user, db) -> models.ConditionCheck:
    check = db.get(models.ConditionCheck, check_id)
    if check is None:
        raise HTTPException(404, "Condition check not found")
    trip = db.get(models.Trip, check.trip_id)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(404, "Condition check not found")
    return check
```
Add `user: models.User = Depends(get_current_user)` to `get_check`, `get_check_status`, `get_check_results`, and `regenerate_summary`, and replace their `db.get(models.ConditionCheck, check_id)` + 404 with `_owned_check(check_id, user, db)`. (Import `models` if not already.) In `regenerate_summary`, the settings call becomes `get_settings(db, check.trip_id_owner)` — fetch the trip and use `get_settings(db, trip.user_id)`; load `trip = db.get(models.Trip, check.trip_id)` (already owned via `_owned_check`).

- [ ] **Step 2: Scope settings routes to the current user**

In `backend/app/routes/misc.py`, add `from ..security import get_current_user`. Update:
```python
@router.get("/settings", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    s = get_settings(db, user.id)
    s["api_keys_present"] = api_keys_present(db)
    return SettingsOut(**s)


@router.post("/settings", response_model=SettingsOut)
def write_settings(body: SettingsUpdate, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    data = body.model_dump(exclude_unset=True)
    data.pop("api_keys", None)
    s = update_settings(db, user.id, data)
    s["api_keys_present"] = api_keys_present(db)
    return SettingsOut(**s)
```
Leave `search_location` and `health` PUBLIC (no `get_current_user`). Scope the agent run-all:
```python
@router.post("/agent/run-all-saved-trips")
def run_all(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    check_ids = jobs.run_all_saved_trips(user.id)
    return {"started_condition_checks": check_ids}
```

- [ ] **Step 3: Scope `run_all_saved_trips` in jobs**

In `backend/app/agent/jobs.py`:
```python
def run_all_saved_trips(user_id: int) -> list[int]:
    db = SessionLocal()
    try:
        trip_ids = [t.id for t in db.query(models.Trip)
                    .filter(models.Trip.user_id == user_id).all()]
    finally:
        db.close()
    return [start_condition_check(tid) for tid in trip_ids]
```

- [ ] **Step 4: Confirm import**

Run: `cd backend && .venv/Scripts/python -c "from app.main import app; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/checks.py backend/app/routes/misc.py backend/app/agent/jobs.py
git commit -m "feat(checks/settings): scope to owner; keep search/health public; scope run-all"
```

## Task 12: Isolation tests + update existing tests to authenticate

**Files:**
- Create: `backend/tests/test_isolation.py`
- Modify: `backend/tests/test_app.py`, `test_routes_settings.py`, `test_report_robustness.py`, `test_api_contracts.py`

- [ ] **Step 1: Write isolation + public-endpoint tests**

Create `backend/tests/test_isolation.py`:
```python
"""Cross-user isolation and public-endpoint access."""
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "iso.db"))
os.environ.setdefault("SIGNUP_CODE", "test-invite-code")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from tests.conftest import signup_and_token  # noqa: E402

_cm = TestClient(app)
client = _cm.__enter__()


def teardown_module(_m):
    _cm.__exit__(None, None, None)


def test_new_user_gets_sample_trips():
    _t, _uid, headers = signup_and_token(client, "seed@example.com")
    trips = client.get("/trips", headers=headers).json()
    assert len(trips) == 4  # seeded on signup


def test_protected_endpoints_require_auth():
    assert client.get("/trips").status_code == 401
    assert client.get("/settings").status_code == 401


def test_public_endpoints_need_no_auth():
    assert client.get("/health").status_code == 200
    r = client.post("/search/location", json={"query": "46.85, -121.76"})
    assert r.status_code == 200 and "results" in r.json()


def test_user_cannot_touch_another_users_trip():
    _t1, _u1, h1 = signup_and_token(client, "owner@example.com")
    created = client.post("/trips", headers=h1, json={
        "name": "Mine", "latitude": 47.0, "longitude": -121.0,
        "start_date": "2026-07-01", "end_date": "2026-07-03"}).json()
    tid = created["id"]

    _t2, _u2, h2 = signup_and_token(client, "intruder@example.com")
    assert client.get(f"/trips/{tid}", headers=h2).status_code == 404
    assert client.patch(f"/trips/{tid}", headers=h2, json={"notes": "x"}).status_code == 404
    assert client.delete(f"/trips/{tid}", headers=h2).status_code == 404
    assert client.post(f"/trips/{tid}/run-condition-check", headers=h2).status_code == 404
    # Owner still sees it; intruder's trip list does not include it.
    assert any(t["id"] == tid for t in client.get("/trips", headers=h1).json())
    assert all(t["id"] != tid for t in client.get("/trips", headers=h2).json())
```

- [ ] **Step 2: Update existing API tests to authenticate**

The following tests call now-protected endpoints. Add auth headers via the helper.

In `backend/tests/test_app.py`: at the top of the module add `from tests.conftest import signup_and_token` and create a module-level authenticated session once after the client is created:
```python
_TOKEN, _UID, AUTH = signup_and_token(client, "testapp@example.com")
```
Then:
- `test_seeded_trips_and_crud`: replace the global-seed assertion. New body:
```python
def test_seeded_trips_and_crud():
    r = client.get("/trips", headers=AUTH)
    assert r.status_code == 200
    assert len(r.json()) >= 4  # seeded on this user's signup
    r = client.post("/trips", headers=AUTH, json={
        "name": "Test trip", "location_name": "Somewhere, WA",
        "latitude": 47.0, "longitude": -121.0,
        "start_date": "2026-07-01", "end_date": "2026-07-03",
        "trip_type": "backpacking"})
    assert r.status_code == 200
    tid = r.json()["id"]
    r = client.patch(f"/trips/{tid}", headers=AUTH, json={"notes": "updated"})
    assert r.json()["notes"] == "updated"
    assert client.delete(f"/trips/{tid}", headers=AUTH).status_code == 200
```
- `test_gpx_parse_and_upload`: add `headers=AUTH` to the `client.get("/trips")` and the upload `client.post(...)` calls.
- `test_settings_roundtrip`: add `headers=AUTH` to the POST.
- `test_print_report_route`: add `headers=AUTH` to the `/trips` GET; the print-report GET is auth-protected too, so add `headers=AUTH`.

In `backend/tests/test_routes_settings.py`: add `from tests.conftest import signup_and_token`, create `_T,_U,AUTH = signup_and_token(client, "settings@example.com")`, and add `headers=AUTH` to the trip POST/PATCH and the `client.get`/`post` `/settings` style calls. (The `test_get_settings_keeps_default_on_unparseable_value` uses the `session` fixture + the service directly — update it to pass a `user_id`: create a user row in the in-memory session and call `get_settings(session, user_id)`.) New body:
```python
def test_get_settings_keeps_default_on_unparseable_value(session):
    from app import models
    from app.security import hash_password
    u = models.User(email="x@y.com", password_hash=hash_password("password123"))
    session.add(u); session.commit()
    session.add(models.AppSetting(user_id=u.id, key="connectors_enabled", value="not-json{"))
    session.commit()
    out = get_settings(session, u.id)
    assert isinstance(out["connectors_enabled"], dict)
    assert out["connectors_enabled"].get("nws_weather") is True
```

In `backend/tests/test_report_robustness.py`: `test_print_report_bad_check_id_returns_404` calls `/trips` and the print-report route, both protected. Add `from tests.conftest import signup_and_token`, `_T,_U,AUTH = signup_and_token(client, "report@example.com")`, and `headers=AUTH` on those calls. The two `generate_report_html` unit tests construct models directly and need a `user_id` on the `Trip(...)` (set `user_id=1`) but do not hit the API, so just add `user_id=1` to those `models.Trip(...)` constructions to satisfy NOT NULL when flushed (they are not flushed; still add for correctness).

In `backend/tests/test_api_contracts.py`: `test_run_condition_check_returns_check_with_id` calls `/trips` and `run-condition-check` (protected). Add the helper + `AUTH` and `headers=AUTH`. The `get_check` tests build rows directly via `SessionLocal`; set `user_id` when creating the `Trip`/use an existing seeded trip's id. Simplest: create the trip via the API with `headers=AUTH`, then create the check rows against that trip id. `test_search_location_returns_results_envelope` stays unauthenticated (search is public).

- [ ] **Step 3: Run the full suite**

Run: `cd backend && .venv/Scripts/python -m pytest tests/ -q`
Expected: all PASS (isolation, auth, per-user settings, and updated existing tests).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test: cross-user isolation; authenticate existing API tests"
```

---

# STAGE 4 — Frontend auth + UX

## Task 13: API client, types, and auth context

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/lib/auth.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Make `api.ts` env-based, token-aware, with auth endpoints**

In `frontend/src/lib/api.ts`:
- Replace `export const API_BASE = "http://localhost:8000";` with:
```typescript
export const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

const TOKEN_KEY = "summitsignal_token";
export function getToken(): string | null { return localStorage.getItem(TOKEN_KEY); }
export function setToken(t: string | null) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}
```
- In `request`, attach the token and treat 401 as a session expiry. Update the headers and add 401 handling:
```typescript
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers || {}),
      },
      ...init,
    });
  } catch {
    throw new Error("Backend unreachable. Is the server running?");
  }
  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event("summitsignal-unauthorized"));
    throw new Error("Your session expired. Please log in again.");
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch { /* keep default */ }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}
```
- Add auth methods to the `api` object and remove `ollamaModels`:
```typescript
  signup: (email: string, password: string, invite_code: string) =>
    request<{ token: string; user: User }>("/auth/signup", {
      method: "POST", body: JSON.stringify({ email, password, invite_code }) }),
  login: (email: string, password: string) =>
    request<{ token: string; user: User }>("/auth/login", {
      method: "POST", body: JSON.stringify({ email, password }) }),
  me: () => request<User>("/auth/me"),
```
Delete the `ollamaModels` method. Import `User` from `../types`.
- The `printReportUrl` helper builds a plain URL the browser opens directly; since the report route is now auth-protected and a bare `<a>`/`window.open` cannot send the Authorization header, change the report link to fetch the HTML with the token and open it as a blob. Add:
```typescript
  fetchReportHtml: async (tripId: number, checkId?: number): Promise<string> => {
    const q = checkId ? `?check_id=${checkId}` : "";
    const token = getToken();
    const res = await fetch(`${API_BASE}/trips/${tripId}/print-report${q}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Report failed (${res.status})`);
    return res.text();
  },
```
Keep `printReportUrl` for now but it will be replaced at call sites in Task 15.

- [ ] **Step 2: Update `types.ts`**

In `frontend/src/types.ts`:
- Add: `export interface User { id: number; email: string; }`
- In `AppSettings`, remove `ollama_enabled`, `ollama_url`, `ollama_model`, `schedule_hours`.
- In `SettingsUpdate`, it extends `Partial<Omit<AppSettings, "api_keys_present">>`; since those fields are gone from `AppSettings` they drop automatically. Keep `api_keys?` removed too: change `SettingsUpdate` to `export interface SettingsUpdate extends Partial<Omit<AppSettings, "api_keys_present">> {}` (drop the `api_keys` line).

- [ ] **Step 3: Create the auth context `frontend/src/lib/auth.tsx`**

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { User } from "../types";
import { api, getToken, setToken } from "./api";

interface AuthState {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, code: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) { setReady(true); return; }
    api.me().then(setUser).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);

  useEffect(() => {
    const onUnauthorized = () => setUser(null);
    window.addEventListener("summitsignal-unauthorized", onUnauthorized);
    return () => window.removeEventListener("summitsignal-unauthorized", onUnauthorized);
  }, []);

  async function login(email: string, password: string) {
    const { token, user } = await api.login(email, password);
    setToken(token); setUser(user);
  }
  async function signup(email: string, password: string, code: string) {
    const { token, user } = await api.signup(email, password, code);
    setToken(token); setUser(user);
  }
  function logout() { setToken(null); setUser(null); }

  return (
    <AuthContext.Provider value={{ user, ready, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
```

- [ ] **Step 4: Wrap `App` in `AuthProvider`**

In `frontend/src/main.tsx`, wrap `<App/>` inside `<AuthProvider>` (inside the existing `<ErrorBoundary>`):
```tsx
import { AuthProvider } from "./lib/auth";
// ...
  <React.StrictMode>
    <ErrorBoundary>
      <AuthProvider>
        <App />
      </AuthProvider>
    </ErrorBoundary>
  </React.StrictMode>,
```

- [ ] **Step 5: Build**

Run: `cd frontend && npm run build`
Expected: compiles (call sites for removed settings fields are fixed in Task 16; if the build flags `ollama_*`/`schedule_hours`/`ollamaModels` usage in `SettingsView.tsx` or `App.tsx`, that is expected and fixed in Task 16, but to keep this task green, also do Task 16's SettingsView edit now if the compiler blocks the build). 

> To keep each task's build green, defer this `npm run build` verification to after Task 16, OR remove the now-dangling `ollama`/`schedule`/`ollamaModels` references in `SettingsView.tsx` as part of this step. Recommended: do the SettingsView cleanup (Task 16) immediately after this task; run the build once at the end of Task 16.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/types.ts frontend/src/lib/auth.tsx frontend/src/main.tsx
git commit -m "feat(frontend): env API base, token-aware client, auth context"
```

## Task 14: Login/signup screen

**Files:**
- Create: `frontend/src/components/AuthScreen.tsx`

- [ ] **Step 1: Create the auth screen**

```tsx
import { useState } from "react";
import { useAuth } from "../lib/auth";

export default function AuthScreen() {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      if (mode === "login") await login(email, password);
      else await signup(email, password, code);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen" style={{ maxWidth: 360, margin: "8vh auto", padding: 24 }}>
      <h1 style={{ marginBottom: 4 }}>SummitSignal</h1>
      <p style={{ color: "var(--ink-soft)", marginTop: 0 }}>
        {mode === "login" ? "Log in to see your trips." : "Create an account (invite code required)."}
      </p>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <input type="email" placeholder="Email" value={email} required
               onChange={(e) => setEmail(e.target.value)} />
        <input type="password" placeholder="Password (min 8 chars)" value={password} required
               minLength={8} onChange={(e) => setPassword(e.target.value)} />
        {mode === "signup" && (
          <input type="text" placeholder="Invite code" value={code} required
                 onChange={(e) => setCode(e.target.value)} />
        )}
        {error && <div className="error-note">{error}</div>}
        <button className="btn primary" disabled={busy} type="submit">
          {busy ? "..." : mode === "login" ? "Log in" : "Sign up"}
        </button>
      </form>
      <button className="btn ghost small" style={{ marginTop: 10 }}
              onClick={() => { setError(null); setMode(mode === "login" ? "signup" : "login"); }}>
        {mode === "login" ? "Need an account? Sign up" : "Have an account? Log in"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/AuthScreen.tsx
git commit -m "feat(frontend): login/signup screen"
```

## Task 15: Gate panels in App; header login/logout; report link via token

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/TripDetail.tsx` (report link)

- [ ] **Step 1: Wire auth into `App.tsx`**

In `frontend/src/App.tsx`:
- Import: `import { useAuth } from "./lib/auth"; import AuthScreen from "./components/AuthScreen";`
- Inside `App()`, near the top: `const { user, ready, logout } = useAuth();`
- The boot effect should only load trips/settings when logged in. Change the boot effect to:
```tsx
  useEffect(() => {
    api.health().then(() => setBackendOk(true)).catch(() => setBackendOk(false));
    const iv = window.setInterval(
      () => api.health().then(() => setBackendOk(true)).catch(() => setBackendOk(false)), 20000);
    return () => window.clearInterval(iv);
  }, []);

  useEffect(() => {
    if (!user) { setTrips([]); setSelectedTrip(null); setCheck(null); return; }
    api.listTrips().then(setTrips).catch(() => {});
    api.getSettings().then(setSettings).catch(() => {});
  }, [user]);
```
- In the header nav, add a login/logout control:
```tsx
        <nav className="topbar-nav">
          <button className={view === "dashboard" ? "active" : ""} onClick={() => setView("dashboard")}>Map</button>
          {user && <button className={view === "settings" ? "active" : ""} onClick={() => setView("settings")}>Settings</button>}
          {user
            ? <button onClick={() => { logout(); setView("dashboard"); }}>Log out ({user.email})</button>
            : <button onClick={() => setView("dashboard")}>Log in</button>}
        </nav>
```
- Gate the left "New trip" + "Saved trips" panels and the right dashboard. The map (`panel-center`) renders for everyone. Where the left panel renders `TripForm`/`SavedTrips`, wrap with a logged-out prompt:
```tsx
            {user ? (
              <>
                <div className="section">
                  <h2 className="section-title">New trip</h2>
                  <TripForm selectedPoint={selectedPoint} locationName={pointName} onCreated={onTripCreated} />
                </div>
                <div className="section">
                  <h2 className="section-title">Saved trips ({trips.length})</h2>
                  <SavedTrips trips={trips} selectedTripId={selectedTrip?.id ?? null}
                              onSelect={selectTrip} onOpenDetail={(t) => { setDetailTrip(t); setView("detail"); }}
                              onRunAll={runAll} runningAll={runningAll} />
                </div>
              </>
            ) : (
              <div className="section">
                <div className="empty-note">Log in to save trips and run condition checks. You can browse and search the map without an account.</div>
                <button className="btn primary" style={{ marginTop: 8 }} onClick={() => setView("auth")}>Log in / Sign up</button>
              </div>
            )}
```
- Add an `"auth"` view: extend the `View` type to `"dashboard" | "detail" | "settings" | "auth"`, and render `{view === "auth" && !user && <AuthScreen />}`. After a successful login `user` becomes set; add an effect to bounce away from the auth view once logged in: `useEffect(() => { if (user && view === "auth") setView("dashboard"); }, [user, view]);`
- Gate the right `ConditionDashboard`: render it only when `user`; otherwise render a short "Log in to run checks" note in `panel-right`.
- The settings view: render `{view === "settings" && user && <SettingsView .../>}`.
- Guard against `ready === false` (initial token check): `if (!ready) return <div className="empty-note" style={{ padding: 40 }}>Loading...</div>;` near the top of the returned JSX, before the shell, OR show the shell with a spinner. Simplest: `if (!ready) return null;` at the very top of `App`'s return.

- [ ] **Step 2: Fix the report link to send the token (TripDetail)**

In `frontend/src/components/TripDetail.tsx`, the "Print / export report" link uses `api.printReportUrl(...)` in a bare `<a>`. Replace it with a button that fetches the HTML with the token and opens it in a new tab:
```tsx
            {activeCheck && (
              <button className="btn full" onClick={async () => {
                try {
                  const html = await api.fetchReportHtml(trip.id, activeCheck.id);
                  const blob = new Blob([html], { type: "text/html" });
                  window.open(URL.createObjectURL(blob), "_blank");
                } catch (e) { setError((e as Error).message); }
              }}>
                Print / export report
              </button>
            )}
```
Apply the same change to the "Print report" link in `ConditionDashboard.tsx` (replace the `<a href={api.printReportUrl(...)}>` with the same fetch-blob button pattern).

- [ ] **Step 3: Build (with Task 16 applied)**

Run after Task 16: `cd frontend && npm run build`. (Build verification is consolidated at the end of Task 16 since SettingsView still references removed fields until then.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/TripDetail.tsx frontend/src/components/ConditionDashboard.tsx
git commit -m "feat(frontend): public map, gate trip/dashboard/settings behind login; tokenized report"
```

## Task 16: Settings UI cleanup + 12h staleness nudge

**Files:**
- Modify: `frontend/src/components/SettingsView.tsx`
- Modify: `frontend/src/components/ConditionDashboard.tsx`
- Modify: `frontend/src/components/SavedTrips.tsx`

- [ ] **Step 1: Remove API-key and Ollama/schedule sections from `SettingsView.tsx`**

Delete the `KEYED` constant, the `keys`/`setKeys`, `ollamaModels`, `ollamaAvailable` state, the `useEffect` that calls `api.ollamaModels`, the "API keys" `settings-card`, and the "Local LLM (Ollama) & schedule" `settings-card`. In `save()`, remove `ollama_enabled/ollama_url/ollama_model/schedule_hours` from the `payload` and remove the `api_keys` block. Update the intro `<p>` to: "Your settings are saved to your account. Source API keys are configured by the operator." Keep the Connectors and Thresholds cards.

- [ ] **Step 2: Add the 12h staleness nudge to `ConditionDashboard.tsx`**

Add a helper near the top of the file:
```tsx
const STALE_HOURS = 12;
function checkAgeHours(iso: string | null | undefined): number | null {
  if (!iso) return null;
  return (Date.now() - new Date(iso).getTime()) / 3600000;
}
```
In the dashboard body (when `trip` is set), above the Run button block, add the nudge using the trip's `last_checked_at`:
```tsx
        {(() => {
          const age = checkAgeHours(trip.last_checked_at);
          if (age === null) return (
            <div className="error-note" style={{ background: "#f3efe7", color: "#5f5320", borderColor: "#d8cda8" }}>
              No condition check yet. Run one for current conditions.
            </div>
          );
          if (age > STALE_HOURS) return (
            <div className="error-note" style={{ background: "#f3efe7", color: "#5f5320", borderColor: "#d8cda8" }}>
              Conditions last checked {Math.round(age)}h ago. Re-run for current data.
            </div>
          );
          return null;
        })()}
```
(`Trip.last_checked_at` already exists in the `Trip` type and is returned by the API.)

- [ ] **Step 3: Add a stale dot to `SavedTrips.tsx`**

In `frontend/src/components/SavedTrips.tsx`, for each trip row, show a small indicator when the trip's last check is null or older than 12h. Add near the trip name render:
```tsx
{(() => {
  const iso = t.last_checked_at;
  const stale = !iso || (Date.now() - new Date(iso).getTime()) / 3600000 > 12;
  return stale ? <span title="No recent check (>12h)" style={{ color: "#b3261e", marginLeft: 6 }}>●</span> : null;
})()}
```
(Place it inside the existing per-trip row markup next to the trip name; adapt to the row's structure.)

- [ ] **Step 4: Build the frontend (consolidated verification)**

Run: `cd frontend && npm run build`
Expected: TypeScript compiles with no errors. (All removed-field references are now gone.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SettingsView.tsx frontend/src/components/ConditionDashboard.tsx frontend/src/components/SavedTrips.tsx
git commit -m "feat(frontend): per-account settings UI cleanup; 12h staleness nudge"
```

- [ ] **Step 6: Manual verification (documented)**

With backend running (`uvicorn app.main:app --reload --port 8000`, env `SIGNUP_CODE=test`) and `npm run dev`:
1. Logged out: the map, basemap toggle, and search work; the left panel shows "Log in to save trips"; the right panel prompts to log in.
2. Sign up with the invite code: 4 sample trips appear; selecting one shows the dashboard.
3. A trip with no check (or >12h) shows the nudge; running a check clears it.
4. Log out and back in: trips persist (same account).
5. A second account sees only its own trips.

---

# STAGE 5 — Em-dash sweep

## Task 17: Remove all em dashes

**Files:**
- Modify: every file containing U+2014 under `backend/app`, `frontend/src`, and `README.md`.

- [ ] **Step 1: Inventory**

Run: `cd c:/Users/jacob/summit-signal && grep -rn $'—' --include="*.py" --include="*.ts" --include="*.tsx" --include="*.css" --include="*.md" backend/app frontend/src README.md`
Expected: a list of every em dash and its context.

- [ ] **Step 2: Replace, file by file**

For each occurrence, replace the em dash with the best-reading substitute:
- In prose (comments, docstrings, summary/report strings, README): a comma, parentheses, or a spaced hyphen `" - "` depending on the sentence.
- UI empty-value placeholders rendered to users (e.g. `"—"` strings in `Badges.tsx`, `TripDetail.tsx`, `ConditionDashboard.tsx`, `api.ts fmtTime` returning `"—"`): replace with `"-"`.
- In `report_generator.py` HTML (`&middot;` separators are fine; replace literal `—` text/separators with `-` or `,`).
Do NOT change behavior, only the dash characters. Keep edits minimal and within strings/comments.

- [ ] **Step 3: Verify none remain**

Run: `cd c:/Users/jacob/summit-signal && grep -rn $'—' --include="*.py" --include="*.ts" --include="*.tsx" --include="*.css" --include="*.md" backend/app frontend/src README.md; echo "exit: $?"`
Expected: no output and `exit: 1` (grep found nothing).

- [ ] **Step 4: Verify nothing broke**

Run: `cd backend && .venv/Scripts/python -m pytest tests/ -q` (all PASS) and `cd frontend && npm run build` (clean).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove all em dashes from code, UI, and docs"
```

---

# STAGE 6 — Deploy config + docs

## Task 18: Deployment artifacts and README

**Files:**
- Create: `backend/render.yaml`, `frontend/vercel.json`, `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Render service config**

Create `backend/render.yaml`:
```yaml
services:
  - type: web
    name: summitsignal-api
    runtime: python
    rootDir: backend
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: JWT_SECRET
        sync: false
      - key: SIGNUP_CODE
        sync: false
      - key: ALLOWED_ORIGINS
        sync: false
      - key: SUMMIT_SIGNAL_FIRMS_KEY
        sync: false
      - key: SUMMIT_SIGNAL_AIRNOW_KEY
        sync: false
      - key: SUMMIT_SIGNAL_NPS_KEY
        sync: false
```

- [ ] **Step 2: Vercel config**

Create `frontend/vercel.json`:
```json
{
  "buildCommand": "npm run build",
  "outputDirectory": "dist",
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```
(The frontend's `VITE_API_BASE` is set in the Vercel project's Environment Variables to the Render backend URL.)

- [ ] **Step 3: Env example**

Create `.env.example` at the repo root:
```
# Backend (Render)
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB
JWT_SECRET=generate-a-long-random-string
SIGNUP_CODE=pick-a-shared-invite-code
ALLOWED_ORIGINS=https://your-frontend.vercel.app
SUMMIT_SIGNAL_FIRMS_KEY=
SUMMIT_SIGNAL_AIRNOW_KEY=
SUMMIT_SIGNAL_NPS_KEY=

# Frontend (Vercel)
VITE_API_BASE=https://your-backend.onrender.com
```

- [ ] **Step 4: Update README**

In `README.md`, replace the "local-first ... no accounts" framing with the hosted, multi-user reality: accounts via invite code, public map browsing, per-user trips, on-demand checks (no scheduler), rule-based summaries (no Ollama), API keys via server env. Add a "Deploying" section pointing at `render.yaml`, `vercel.json`, and `.env.example`, and listing the env vars. Keep the local-dev quick start (SQLite default; set `SIGNUP_CODE` to sign up locally).

- [ ] **Step 5: Final verification**

Run: `cd backend && .venv/Scripts/python -m pytest tests/ -q` (all PASS); `cd frontend && npm run build` (clean); `cd c:/Users/jacob/summit-signal && grep -rn $'—' backend/app frontend/src README.md; echo done` (no em dashes).

- [ ] **Step 6: Commit**

```bash
git add backend/render.yaml frontend/vercel.json .env.example README.md
git commit -m "docs(deploy): Render/Vercel config, env example, README for hosted multi-user"
```

---

## Self-Review

**Spec coverage (every spec section maps to a task):**
- Architecture & deployment (env config, dialect-guard pragmas, secrets) -> Tasks 1, 2, 18.
- Auth & accounts (users, bcrypt, JWT, signup/login/me, invite code) -> Tasks 6, 7, 8.
- Public vs protected (search/health public; rest protected) -> Tasks 11, 12.
- Per-user isolation (Trip.user_id, scoping, 404, seed-on-signup) -> Tasks 8, 9, 10, 11, 12.
- Settings/API keys/Ollama/scheduler (env keys, per-user settings, drop Ollama, drop scheduler) -> Tasks 2, 3, 4, 5, 9, 11, 16.
- 12h staleness nudge -> Task 16.
- Em-dash sweep -> Task 17.
- Postgres portability -> Task 1.
- Testing (auth, isolation, per-user settings, existing tests authenticated) -> Tasks 8, 9, 12.
- Frontend auth + gating + report tokenization -> Tasks 13, 14, 15, 16.

**Placeholder scan:** The only forward-references are explicit sequencing notes (e.g. "verify at the end of Task 9", "build at end of Task 16") with concrete reasons, not vague TODOs. The Task 2 stub router is concrete code, restored in Task 8. No "add error handling"-style placeholders.

**Type/name consistency:** `get_current_user` (security.py) used identically in trips/checks/misc; `_owned_trip`/`_owned_check` helpers named consistently; `get_settings(db, user_id)`/`update_settings(db, user_id, updates)` signatures consistent across Tasks 9/10/11; frontend `getToken`/`setToken`/`useAuth`/`fetchReportHtml` consistent across Tasks 13/15/16; `User` type consistent (backend `UserOut` {id,email} == frontend `User`).

**Sequencing caveats (carry into execution):**
- Several backend tests are intentionally green only at stage boundaries (auth tests pass after Task 9; existing API tests pass after Task 12). Run the FULL suite at the end of Tasks 9 and 12, not mid-task.
- Frontend builds are consolidated at the end of Task 16 (removed-field references span Tasks 13-16).
- Introducing `users`/`Trip.user_id` changes the schema with no Alembic: delete the local dev `summit_signal.db` before first run after Task 9 (`Base.metadata.create_all` only creates missing tables; it will NOT add `user_id` to an existing `trips` table). Document: drop/recreate the dev DB after Task 9.
