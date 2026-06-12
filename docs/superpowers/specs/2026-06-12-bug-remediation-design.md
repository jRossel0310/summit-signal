# SummitSignal — Bug Remediation Design

**Date:** 2026-06-12
**Status:** Approved scope, pending spec review
**Owner:** (implementation TBD)

## Purpose

A four-area audit (backend connectors, services, agent/routes/core, frontend) found
a set of verified bugs ranging from data-loss and request lockups to crashes and
incorrect status reporting. This document specifies the fixes, grouped into themed
batches, each delivered with a regression test where practical.

### Scope decisions (agreed)

- **Coverage:** fix everything — all HIGH, MEDIUM, and LOW findings. LOW cosmetic
  items are included, not deferred.
- **Delivery:** themed batches (one logical commit per batch), each with a regression
  test where the existing offline `pytest` suite or a frontend check can cover it.
- **Concurrency posture:** *pragmatic hardening*. Keep the existing threaded pipeline;
  add `busy_timeout` + WAL, bound the scheduled job, and cap worker-thread concurrency.
  Do **not** rewrite the pipeline into a queue/pool in this effort.

### Out of scope

- Rearchitecting the connector pipeline into a managed worker pool/queue.
- New features, new connectors, or UI redesign.
- Auth, deployment, or multi-user concerns.

### Non-bugs confirmed during audit (do not "fix")

Recorded so they are not re-investigated: lat/lon ordering (all call sites correct),
point-in-polygon ray-casting math, Markdown rendering (no `dangerouslySetInnerHTML`;
link scheme restricted), MapView StrictMode cleanup, the `status="complete"` string
match between `jobs.py` and `print_report`, and GPX `ParseError` handling (the
`upload-gpx` route already wraps parsing in a broad `except` → HTTP 400).

---

## Batches

Each batch lists the bugs, the fix, and the verification. Severities: HIGH / MED / LOW.

### Batch 1 — Persistence & cascade integrity (backend)

**Goal:** deleting a trip must remove all descendant rows; no orphaned data.

- **[HIGH] `delete_trip` orphans child rows** — `backend/app/routes/trips.py:96-98`
  `db.query(ConditionCheck).filter_by(trip_id=...).delete()` is a bulk delete that
  bypasses ORM cascades, leaving `ConnectorResult`, `RiskFlag`, `AiSummary`, and
  `SavedReport` rows orphaned.
  **Fix:** remove the bulk delete; rely on `db.delete(trip)` with ORM cascade.

- **[MED] Missing FK/cascade on `AiSummary` & `SavedReport`** — `backend/app/models.py`
  `SavedReport.condition_check_id` is a plain `Integer`, not a `ForeignKey`; neither
  `AiSummary` nor `SavedReport` cascade-deletes with its parent.
  **Fix:** declare `SavedReport.condition_check_id` as a `ForeignKey`; add
  relationship/cascade (or `ondelete`) so summaries and saved reports are removed when
  their parent check/trip is deleted. Enable SQLite FK enforcement
  (`PRAGMA foreign_keys=ON`) so cascades and constraints actually apply — coordinate
  with the engine `PRAGMA` work in Batch 2.

**Verification:** pytest — create a trip with a completed check (connector results,
risk flags, AI summary, saved report), delete the trip, assert zero descendant rows
remain in every child table.

---

### Batch 2 — Concurrency & reliability (backend agent pipeline)

**Goal:** concurrent checks don't deadlock the DB or pile up threads; a deleted
trip/check never leaves a check stuck "running".

- **[HIGH] No SQLite busy timeout** — `backend/app/database.py:11-14`
  `connect_args={"check_same_thread": False}` has no `timeout`; concurrent worker
  commits raise `database is locked` immediately.
  **Fix:** add `connect_args={..., "timeout": 30}`, set
  `PRAGMA busy_timeout=30000`, `PRAGMA journal_mode=WAL`, and
  `PRAGMA foreign_keys=ON` via a connection/`connect` event listener so every
  connection gets them.

- **[HIGH] Scheduler spawns unbounded threads** — `backend/app/agent/scheduler.py:28`
  + `backend/app/agent/jobs.py` (`run_all_saved_trips`). The interval job has no
  `max_instances`, `coalesce`, or `misfire_grace_time`, and each fire spawns one
  unmanaged daemon thread per trip regardless of whether prior runs finished.
  **Fix:** configure the APScheduler job with `max_instances=1`, `coalesce=True`,
  `misfire_grace_time=...`; bound worker-thread concurrency with a small fixed-size
  pool or a semaphore (e.g. cap of N concurrent checks) shared by manual and scheduled
  runs. Keep the threaded design.

- **[HIGH] `_run_check` never None-checks `check`/`trip`** — `backend/app/agent/jobs.py:63-64`
  A deleted check/trip raises `AttributeError`; the broad handler then no-ops when
  `check is None`, leaving the check `"running"` forever and the frontend polling
  indefinitely.
  **Fix:** guard early — `if check is None: return`; `if trip is None:` mark the check
  `failed` with a clear message and return. Ensure the failure path always commits a
  terminal status.

**Verification:** pytest — (a) simulate concurrent `start_condition_check` calls and
assert no `OperationalError`/lock failures and all checks reach a terminal status;
(b) delete the trip before the worker runs and assert the check ends `failed`, not
stuck `running`; (c) assert the scheduler job is registered with the bounded config.

---

### Batch 3 — Risk engine correctness (backend)

**Goal:** completeness reflects only connectors that actually ran and were enabled.

- **[HIGH] Completeness counts skipped/disabled/failed connectors** —
  `backend/app/services/risk_engine.py:73-77`
  `ran = [o for o in outputs]` puts every output in the denominator and ignores the
  `enabled` argument, so disabling an optional connector drops completeness below 0.7
  and wrongly flips overall status to **"Data incomplete."**
  **Fix:** compute completeness over connectors that were enabled and ran
  (`success`/`partial`, plus enabled-but-`failed` as 0); exclude user-`skipped`/
  disabled connectors from both numerator and denominator. Consult the `enabled`
  argument (currently unused). Document the chosen policy in a comment.

**Verification:** pytest — table of connector output mixes (all success; one disabled;
one failed; one skipped) asserting the expected completeness score and overall status
for each.

---

### Batch 4 — Report generation robustness (backend)

**Goal:** report rendering never crashes on partial/missing data and renders legitimate
zero values correctly.

- **[HIGH] Crash on partial weather data** — `backend/app/services/report_generator.py:115-118`
  Direct `p['temperature_f']`, `p['precip_chance']`, etc. raise `KeyError` on partial
  NWS data and abort the whole report.
  **Fix:** use `.get(...)` with explicit fallbacks (`'?'`/`'—'`).

- **[MED] Crash on elevation bands** — `report_generator.py:132-134`
  `b['temp_offset_f']:+.0f` raises `KeyError`/`TypeError` on missing/`None`.
  **Fix:** `.get()` and guard the numeric format (`"?" if off is None else f"{off:+.0f}"`).

- **[MED] `print_report` with no completed check** — `backend/app/routes/trips.py:152-158`
  Passes `None` into the generator (which dereferences GPX/flags) and never 404s a bad
  `check_id`.
  **Fix:** 404 when a provided `check_id` is not found; render a clear
  "no completed check yet" report (or 409/empty state) when none exists, instead of
  dereferencing `None`. Ensure `generate_report_html(trip, None)` is safe.

- **[LOW] Zero values shown as `?`** — `report_generator.py:67-69`
  `gpx.min_elevation_ft or '?'` shows `?` for a legitimate 0 ft (sea level).
  **Fix:** explicit `is not None` checks.

**Verification:** pytest — render a report from (a) a check with partial weather/missing
band keys, (b) `check=None`, (c) a GPX route with 0 ft min elevation; assert no
exception and correct rendering of each.

---

### Batch 5 — Route & settings correctness (backend)

- **[MED] `update_trip` can't clear fields** — `backend/app/routes/trips.py:83-85`
  `if v is not None` blocks nulling any optional field; with `exclude_unset=True` the
  guard is redundant and harmful.
  **Fix:** drop the `if v is not None` guard; rely on `exclude_unset` so explicit
  `null` clears a field. Keep the `elevation_bands` JSON-encode special case.

- **[MED] `get_settings` overwrites dict default with raw string** —
  `backend/app/services/settings_service.py:45-51`
  On JSON-parse failure it assigns the raw string, so a corrupt `connectors_enabled`
  row becomes a string and downstream `.get(...)` raises `AttributeError`.
  **Fix:** on parse failure keep the default (`continue`) or validate the parsed type
  matches the default's type before assigning.

**Verification:** pytest — (a) PATCH a trip setting `notes` to `null` and assert it
clears; (b) seed a corrupt `connectors_enabled` row and assert `get_settings` returns
the default dict, and a downstream `.get` call succeeds.

---

### Batch 6 — Connector correctness (backend)

- **[MED] `elevation_adjusted` drops 0/negative bands** —
  `backend/app/connectors/elevation_adjusted.py` (≈ lines 31, 43, 61)
  Truthiness checks (`if not target`, `if high and ...`, `any(bands.get(k) ...)`) drop
  bands whose elevation is `0` or negative, silently discarding sea-level and
  below-sea-level (e.g. Badwater) trips.
  **Fix:** use explicit `is None` checks throughout.

- **[LOW] `usgs_elevation` mislabels fallback failure** —
  `backend/app/connectors/usgs_elevation.py:62`
  An Open-Meteo fallback failure is reported with the EPQS source label.
  **Fix:** track which source was being attempted and report that source/reason (or
  include both reasons in the message).

**Verification:** pytest — `elevation_adjusted` with a 0 ft / negative trailhead band
asserts the band is retained; `usgs_elevation` fallback-failure path asserts the
correct source label in the failed envelope.

---

### Batch 7 — Frontend state management

**Goal:** switching trips never leaks polling or shows another trip's data; saving
notes doesn't drop nested data; small render glitches fixed.

- **[HIGH] Leaked polling interval on trip-switch** — `frontend/src/App.tsx`
  (`loadLatestCheck` / `beginPolling`). Switching from a polling trip A to a
  non-running trip B never clears A's interval; on A's completion it overwrites B's
  dashboard with A's data.
  **Fix:** at the start of `loadLatestCheck` (or in `selectTrip`), unconditionally
  clear any active poll and reset `running`/`liveStatus` before loading.

- **[MED] `running`/`liveStatus` not reset on switch** — same area — phantom progress
  bar. Folded into the fix above.

- **[MED] Stale-closure `useCallback([])`** — `loadLatestCheck` captures first-render
  `beginPolling`/`refreshTrips`, making the post-poll trip refresh inconsistent between
  the `loadLatestCheck` and `runCheck` entry points.
  **Fix:** correct the dependency list (or move shared functions into refs) so current
  closures are always used; avoid reading `selectedTrip` inside the interval via a
  stale closure (use a ref or functional updater).

- **[MED] Notes-save may drop `gpx_route`** — `frontend/src/components/TripDetail.tsx`
  + `App.tsx` `onTripUpdated`. If the PATCH response isn't hydrated with `gpx_route`,
  replacing the trip wholesale loses the route on the map and detail view.
  **Fix:** confirm the PATCH serializer returns the hydrated trip; if not guaranteed,
  merge in `onTripUpdated` (`{ ...prev, ...updated }`) to preserve nested fields. (The
  backend `_trip_out` should be confirmed to include `gpx_route`.)

- **[LOW] Stale selected-point marker after delete** — `App.tsx` `onTripDeleted` —
  clear `selectedPoint`/`pointName` when the deleted id matches the selection.

- **[LOW] `NaN`/`undefined` renders** — `ConditionDashboard.tsx:49` (`elevation_m`
  unguarded → `NaN m`), `TripDetail.tsx:85-87` (`undefined mi`, `…–0 ft`).
  **Fix:** guard each value with `!= null` and fall back to `—`.

- **[LOW] Index keys** — `SearchBar.tsx:48` — key on a stable composite
  (`lat,lon,display_name`).

**Verification:** since the frontend has no test harness today, verify by manual
reproduction steps documented in the plan (switch trips mid-poll; save notes on a
GPX trip; delete the selected trip; render a connector result missing `elevation_m`).
If a lightweight test setup (Vitest + React Testing Library) is cheap to add, add a
test for the polling-leak fix; otherwise document the manual check.

---

## Risks & sequencing notes

- **Batch ordering:** Batch 1 (cascade) and Batch 2 (`PRAGMA foreign_keys=ON`,
  busy_timeout/WAL) are coupled — enabling FK enforcement changes delete behavior, so
  land them together or Batch 2's PRAGMA work first, then Batch 1's cascade.
- **Existing data:** enabling FK enforcement on an existing `summit_signal.db` with
  pre-existing orphans could surface constraint issues. Plan a note to delete/recreate
  the local dev DB, or run a one-time orphan cleanup.
- **WAL mode** creates `-wal`/`-shm` sidecar files; harmless but note in README if
  relevant.
- Frontend batch has the weakest automated coverage; rely on documented manual repro
  plus an optional targeted test for the polling leak.

## Done criteria

- All listed bugs fixed in their batches.
- Existing `python -m pytest tests/ -q` suite still passes, plus the new regression
  tests above.
- Manual frontend repro steps confirmed.
- No orphaned rows after trip deletion; no `database is locked` under concurrent
  checks; no check left stuck `running`; reports render on partial data; completeness
  unaffected by disabled connectors.
