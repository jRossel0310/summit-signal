# SummitSignal, Multi-User Hosted Deployment Design

**Date:** 2026-06-12
**Status:** Approved scope, pending spec review
**Owner:** (implementation TBD)

## Purpose

Turn SummitSignal from a single-user, local-first app into a small multi-user web
app hosted on free tiers, so a handful of people (the operator plus 2-3 others) can
log in from any device and see their own trips, with data synced through a shared
hosted database. The map stays publicly browsable; only trips, checks, and settings
require an account.

## Goals

- Host the frontend on Vercel and the backend on a free always-on host, backed by a
  shared hosted Postgres, so trips sync across a user's devices.
- Add real accounts: email + password login, self-hosted in the backend.
- Keep every user's trips, checks, and settings private to that user.
- Let logged-out guests browse and search the map, but require login to save trips or
  run checks.
- Nudge a returning user to re-run a check when a trip's last check is over 12 hours old.
- On-demand checks only (no background scheduler).
- Remove all em dashes from the codebase and UI.

## Agreed decisions

- **Topology:** split hosting. Vercel (frontend) + Render free tier (FastAPI backend)
  + Neon free Postgres. The existing background-job + progress-polling check pipeline
  stays as-is, since Render runs a persistent process.
- **Auth:** self-hosted email + password (bcrypt) with a signed JWT bearer token.
- **Signup gating:** a shared invite code (`SIGNUP_CODE` env var) is required to register.
- **Guest access:** logged-out users get the map, basemaps, location search, click-to-see
  coordinates, and layer toggles. Saving a trip or running a check requires login.
- **API keys (FIRMS/AirNow/NPS):** operator-provided **server env vars only**; the
  in-app key-entry UI and DB storage are removed.
- **Per-user settings:** risk thresholds and display settings are stored per user.
- **Ollama:** removed from this build; AI summaries are rule-based only.
- **Scheduler:** removed (APScheduler, `schedule_hours`, schedule routes).
- **Seeding:** the 4 sample trips are seeded into each new account on signup; the global
  startup seeding is removed.
- **Local vs prod DB:** local dev keeps SQLite; prod uses Postgres via `DATABASE_URL`.
  Same code, dialect-guarded.

## Out of scope

- Password reset / email verification flows (no transactional email service). Accounts
  are created via invite code; a forgotten password is handled by the operator (manual
  DB reset) for this small user base. Noted as a future addition.
- Social/OAuth login, multi-factor auth, roles/permissions beyond "owner of a trip."
- Sharing trips between users.
- Ephemeral guest checks (guests cannot run checks).
- Migrating existing local SQLite dev data into prod (prod starts empty).
- httpOnly-cookie sessions (bearer token chosen; revisit if needed).

---

## Architecture & deployment

**Frontend (Vercel):** static Vite build. Two things become environment-driven:
- `VITE_API_BASE` replaces the hardcoded `http://localhost:8000` in `frontend/src/lib/api.ts`.
- The app no longer assumes a local backend; all calls go to `VITE_API_BASE`.

**Backend (Render):** FastAPI as a normal web service.
- `DATABASE_URL` selects the database. When unset, default to the local SQLite file
  (current behavior) so local dev is unchanged; when set to a Postgres URL, use Postgres.
- `ALLOWED_ORIGINS` (comma-separated) replaces the hardcoded localhost CORS list in
  `backend/app/main.py`. Local default includes `http://localhost:5173`.
- The SQLite-only `PRAGMA` connect-listener added previously is guarded to fire only when
  the engine dialect is `sqlite`, so Postgres connections are untouched. `connect_args`
  (`check_same_thread`, `timeout`) are applied only for SQLite.

**Database (Neon):** Postgres. JSON-ish columns remain `Text` (JSON-encoded strings), so
no dialect-specific column types are needed. SQLAlchemy models are otherwise portable.

**Secrets / env vars (documented in README):**
`DATABASE_URL`, `JWT_SECRET`, `SIGNUP_CODE`, `ALLOWED_ORIGINS`,
`SUMMIT_SIGNAL_FIRMS_KEY`, `SUMMIT_SIGNAL_AIRNOW_KEY`, `SUMMIT_SIGNAL_NPS_KEY`.

**Deploy artifacts:**
- `backend/requirements.txt` gains a Postgres driver (`psycopg[binary]`),
  `passlib[bcrypt]`, and `pyjwt`.
- A Render service config (build: `pip install -r requirements.txt`; start:
  `uvicorn app.main:app --host 0.0.0.0 --port $PORT`).
- Vercel project config for the frontend (build `npm run build`, output `dist`,
  `VITE_API_BASE` env var).

---

## Auth & accounts

**Model (`users` table):** `id`, `email` (unique, case-insensitive), `password_hash`
(bcrypt via passlib), `created_at`.

**Password handling:** passlib `CryptContext(schemes=["bcrypt"])` for hash/verify. Plain
passwords never stored or logged. Minimum length enforced (e.g. 8 chars).

**Sessions (JWT bearer):**
- On login, issue an HS256 JWT signed with `JWT_SECRET`, payload `{sub: user_id, exp}`,
  with a sane expiry (e.g. 7 days).
- The frontend stores the token and sends `Authorization: Bearer <token>` on requests.
- A FastAPI dependency `get_current_user` decodes/validates the token and loads the user,
  raising 401 on missing/invalid/expired tokens.
- An optional variant `get_current_user_optional` returns `None` instead of raising, for
  endpoints that work with or without a user (not needed for the public endpoints below,
  but available).

**Endpoints (`/auth`):**
- `POST /auth/signup` -> body `{email, password, invite_code}`. Rejects if `invite_code`
  != `SIGNUP_CODE` (400), or email already exists (409). Creates the user, seeds the 4
  sample trips for them, returns `{token, user}`.
- `POST /auth/login` -> `{email, password}` -> `{token, user}` or 401.
- `GET /auth/me` -> current user (from token) or 401.

`user` shape returned to the client: `{id, email}` (never the hash).

---

## Public vs protected access (guest browsing)

**Public (no auth):**
- `GET /health`
- `POST /search/location` (location search powers guest map browsing)

**Protected (require `get_current_user`):**
- All `/trips...`, all `/condition-checks...`, all `/settings...`, and
  `/agent/run-all-saved-trips`.

**Frontend gating:** the app shell, `MapView`, `SearchBar`, basemap/layer toggles, and the
coordinate readout render regardless of auth state. The **New Trip** form, **Saved Trips**
list, **Condition Dashboard**, **Trip Detail**, and **Settings** are replaced by a
"Log in to save trips and run checks" prompt when logged out. A **Log in / Sign up**
button sits in the header; logging in reveals the gated panels. The fire/perimeter/GPX map
layers simply have no data for a guest (they derive from a selected trip's check), which is
expected.

---

## Per-user data isolation

**Model change:** `trips` gains `user_id` (FK -> `users.id`, `ondelete="CASCADE"`).
Checks, connector results, risk flags, AI summaries, GPX routes, and saved reports all
hang off a trip, so scoping trips by user scopes the whole graph.

**Query scoping:** every trip/check endpoint filters by `current_user.id`. Accessing a
trip or check that exists but belongs to another user returns **404** (not 403, to avoid
leaking existence). Helper: a `get_owned_trip(trip_id, user, db)` / `get_owned_check(...)`
that 404s on miss or wrong owner, used by all relevant routes.

**Seeding on signup:** the 4 sample trips (Mount Rainier, Longs Peak, Yosemite Valley,
Grand Canyon South Rim) are created for the new user inside `POST /auth/signup`. The
global startup `seed()` in `main.py` is removed.

**`locations` table** (search-history logging) is low value and currently global; it is
either scoped to the user or left as anonymous logging. Decision: keep it as anonymous
server-side logging (no user_id), since it is not surfaced per user anywhere. (If it is
ever surfaced, scope it then.)

---

## Settings, API keys, Ollama, scheduler

**External API keys -> server env only.** Remove the `api_keys` table, `set_api_key`, and
the DB path of `get_api_key`; keep `get_api_key` reading the env vars (it already prefers
env). The Settings UI section for entering keys is removed. `api_keys_present` (derived
from env) is retained, read-only, so the UI can show which connectors are configured.

**Per-user settings.** `app_settings` becomes per-user: composite primary key
`(user_id, key)`. `get_settings(db, user)` returns that user's settings merged over the
defaults; `update_settings(db, user, updates)` writes that user's rows. New users inherit
defaults until they change them. The Settings routes require auth and operate on the
current user.

**Ollama removed.** Delete `app/agent/ollama_client.py`, the Ollama branch in
`summarizer.summarize` (always rule-based), the `ollama_enabled/ollama_url/ollama_model`
settings, and `GET /settings/ollama-models`. Remove the Ollama section from `SettingsView`.

**Scheduler removed.** Delete `app/agent/scheduler.py`, `schedule_hours` from settings,
`POST /agent/schedule`, `GET /agent/jobs`, and the scheduler start/shutdown in the
`main.py` lifespan. `POST /agent/run-all-saved-trips` stays but is scoped to the current
user's trips (on-demand "refresh all my trips").

---

## 12-hour staleness nudge

Uses the existing `trips.last_checked_at` (already returned in `TripOut`). Frontend logic:
- **Dashboard:** if the selected trip's `last_checked_at` is null or older than 12 hours,
  show a prominent nudge above the Run button: "Conditions last checked Nh ago, re-run for
  current data." (For never-checked trips: "No check yet, run one for current conditions.")
- **Saved Trips list:** a small "stale" indicator dot on trips whose last check is over 12
  hours old.

No backend change required; the threshold (12h) is a frontend constant.

---

## Em-dash sweep

Replace every em dash (U+2014, ~43 occurrences across ~17 files) with a context-appropriate
substitute:
- Prose em dashes in comments, strings, summaries, the report generator, and docs become a
  comma, parentheses, or a spaced hyphen `" - "`, whichever reads best.
- UI `—` empty-value placeholders (e.g. in Badges, TripDetail) become `-`.

Verification: a repo grep for U+2014 over `backend/app`, `frontend/src`, and `*.md` returns
zero matches.

---

## Postgres portability specifics

- `database.py`: build `engine` from `DATABASE_URL` if set, else the SQLite file URL. Apply
  `connect_args` and register the `PRAGMA` connect-listener only when the URL/dialect is
  SQLite. WAL/`busy_timeout`/`foreign_keys` pragmas are SQLite-only and must not run on
  Postgres.
- Models use portable types (`Integer`, `String`, `Float`, `Text`, `DateTime`, `Boolean`,
  `ForeignKey`). No SQLite-specific types. JSON stays `Text`.
- `Base.metadata.create_all` runs at startup against whichever DB is configured (no Alembic
  for this scope; the schema is created fresh on first deploy).

---

## Testing

Extend the existing offline pytest suite (still on SQLite, dialect-guarded):
- **Auth:** signup requires the correct invite code (wrong/missing -> 400); duplicate email
  -> 409; login returns a token; `get_current_user` accepts a valid token and rejects
  missing/garbage/expired tokens (401); `/auth/me` round-trips.
- **Isolation:** user A cannot read, update, delete, run-check, or print-report another
  user's trip or check (all -> 404); listing trips returns only the caller's trips.
- **Public endpoints:** `/health` and `/search/location` work without a token; protected
  endpoints return 401 without a token.
- **Seed on signup:** a new user starts with the 4 sample trips.
- **Per-user settings:** user A's settings change does not affect user B; defaults apply
  until changed.
- **Portability smoke:** app imports and `create_all` succeeds; the SQLite pragma listener
  is registered only for SQLite (guard is exercised).

**Existing tests must be updated.** Several current tests hit endpoints that become
auth-protected (`/trips`, `/settings`, `run-condition-check`, `print-report`,
`/condition-checks/*`) and assume global seeding (`test_seeded_trips_and_crud` asserts
>= 4 seeded trips). These are updated to authenticate via a shared fixture that signs up a
user (with the test invite code) and attaches the bearer token, and to expect per-user
seeded trips instead of global ones. `/search/location` and `/health` tests stay
unauthenticated. A test `SIGNUP_CODE` is set in the test environment.

Frontend has no automated harness; verify the gating and nudge by `npm run build` plus
documented manual repro (guest sees map + login prompt; logged-in sees panels; stale trip
shows the nudge).

---

## Staged implementation outline

The plan will sequence the work so each stage is independently testable:

1. **DB portability + teardown.** `DATABASE_URL`/`ALLOWED_ORIGINS` config, dialect-guard the
   pragmas, add the Postgres driver. Remove the scheduler and Ollama. Remove global startup
   seeding (temporarily leaving no seed; re-added in stage 3).
2. **Auth foundation.** `users` table, password hashing, JWT issue/verify, `get_current_user`,
   `/auth/signup|login|me`, invite-code gating.
3. **Per-user data + settings.** `trips.user_id`, `get_owned_*` helpers, scope all trip/check
   routes, seed-samples-on-signup, per-user `app_settings`, API keys -> env (remove table/UI
   path), scope `run-all-saved-trips`. Mark `/search/location` and `/health` public.
4. **Frontend auth + UX.** Auth context + login/signup screen, token storage and
   `Authorization` header, 401 -> login, header login/logout, gate the trip/dashboard/settings
   panels (public map/search), remove Ollama + API-key settings UI, add the 12h nudge.
5. **Em-dash sweep.**
6. **Deploy config + docs.** requirements, Render/Vercel config, env-var README, README
   updates (no longer "local-first; no accounts").

## Risks & sequencing notes

- **Schema reset:** introducing `users` and `trips.user_id` changes the schema. With no
  Alembic, the dev SQLite DB should be deleted/recreated, and prod Postgres starts fresh.
  Document this.
- **Token security:** bearer token in browser storage is XSS-readable; mitigated by HTTPS,
  a bounded expiry, and the earlier XSS-safety work (no `dangerouslySetInnerHTML`). httpOnly
  cookies remain a future hardening option.
- **Guest search abuse:** `/search/location` proxies Nominatim unauthenticated; fine at this
  scale, but could be rate-limited or auth-gated later if abused.
- **Render cold start:** free tier sleeps after idle; the first request after idle takes
  ~50s. Acceptable for on-demand use; the UI already surfaces a "backend unreachable" state
  and should tolerate the delay.
- **Forgotten passwords:** no reset flow in scope; operator resets manually. Acceptable for
  3-4 known users.

## Done criteria

- Logged-out users can browse/search the map; trip/check/settings actions prompt for login.
- Signup requires the invite code; login issues a working token; a new account starts with
  the 4 sample trips.
- A user only ever sees and acts on their own trips/checks/settings; cross-user access 404s.
- Checks run on demand; no scheduler; summaries are rule-based; API keys come from env.
- A trip with a check older than 12h shows the re-run nudge.
- No em dashes remain in the codebase.
- App runs on SQLite locally and Postgres in prod (pragmas guarded); existing pytest suite
  plus the new auth/isolation tests pass.
- Frontend builds; documented manual repro of guest vs logged-in and the nudge passes.
