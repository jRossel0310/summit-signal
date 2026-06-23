# SummitSignal

A **hosted, multi-user U.S. hiking, backpacking, and mountaineering trip-condition dashboard**. Pick a point on the map, save a trip, and run a real condition check against live government and public data sources. SummitSignal surfaces concern flags, data gaps, source links with timestamps, a manual verification checklist, an AI-assisted planning summary, and a printable report.

> **Disclaimer:** This tool highlights planning concerns from available sources. It does not determine whether a trip is safe. It never makes go/no-go decisions, it only reports: *No major concerns found · Some concerns found · Major concerns found · Data incomplete · Source check failed.*

Users sign in with email and password (invite-code signup). Each user's trips are private. The map and location search are publicly browsable without an account.

Data is stored in a database (SQLite for local development, Postgres in production). API keys are configured by the operator via server environment variables.

---

## Quick start (two commands)

Requires **Python 3.10+** and **Node 18+**.

**Terminal 1,   backend (port 8000):**

```bash
cd backend
pip install -r requirements.txt
export SIGNUP_CODE=dev-code
uvicorn app.main:app --reload --port 8000
```

**Terminal 2,   frontend (port 5173):**

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Sign up using the invite code you set as `SIGNUP_CODE`. Once logged in, save a trip and click **Run condition check**.

The frontend reads `VITE_API_BASE` (defaults to `http://localhost:8000`) for the backend URL. For local dev, no `DATABASE_URL` is needed - SQLite is used automatically.

> Optional: use a Python virtual environment first (`python -m venv .venv && source .venv/bin/activate`).

---

## What a condition check does

A background job on the Python agent runs each connector in sequence, persisting every result as it lands (the UI polls progress live):

| Connector | Source | Key needed? |
|---|---|---|
| NWS Weather | api.weather.gov point -> grid forecast, hourly, active alerts | no |
| USGS Elevation | EPQS (with Open-Meteo fallback, labeled) | no |
| Elevation-Adjusted Weather | Lapse-rate estimate (~3.5 °F/1000 ft) for trailhead/mid/high bands, **clearly labeled estimate, not a forecast** | no |
| NASA FIRMS | VIIRS active fire detections, last 3 days, within your radius / GPX bounding box | yes (free) |
| NIFC/WFIGS | Current interagency fire perimeters; point-in-perimeter test | no |
| AirNow | Current AQI observations (labeled preliminary/unvalidated) | yes (free) |
| NPS Alerts | Alerts/closures for NPS units within ~35 mi; "not applicable" otherwise | yes (free) |
| Avalanche | avalanche.org zone lookup -> links you to the proper forecast center. **No forecast scraping**, manual check is always required for mountaineering/snowy terrain | no |
| Forecast Discussion | Latest NWS AFD for the responsible office, with keyword highlights (wind, snow, freezing level, severe, uncertainty...) | no |

The **risk engine** turns connector output into severity-tagged flags (info / moderate / major / unknown-data-gap) using thresholds you control in Settings, then computes the overall concern status and a data-completeness score. Missing keys, failed sources, and stale data are surfaced as explicit data-gap flags, never silently ignored.

## API keys (all free)

Connectors that need keys are configured by the operator via server environment variables:

```bash
export SUMMIT_SIGNAL_FIRMS_KEY=...    # https://firms.modaps.eosdis.nasa.gov/api/map_key/
export SUMMIT_SIGNAL_AIRNOW_KEY=...   # https://docs.airnowapi.org/account/request/
export SUMMIT_SIGNAL_NPS_KEY=...      # https://www.nps.gov/subjects/developer/get-started.htm
export SUMMIT_SIGNAL_ORS_KEY=...    # https://openrouteservice.org/dev/#/signup
```

Until a key is configured, the corresponding connector shows **"API key needed"** in check results. Nothing is hardcoded.

## AI summaries

Summaries are **rule-based** (always available): builds a structured markdown summary strictly from connector results.

Every summary ends with the disclaimer and a manual verification checklist (avalanche forecast, permits, land-manager pages, re-check within 24 h of departure, etc.).

## Other features

- **Map** (MapLibre GL): OpenTopoMap/OSM basemaps, search by name or `lat, lon`, click-to-select, saved-trip markers, GPX route display, FIRMS detection dots, WFIGS perimeter polygons, per-layer toggles.
- **Map layers:** floating Layers control with five basemaps (street / satellite / topo / hybrid / dark), per-overlay visibility + opacity, and legends. Basemaps run fully free with no API key; set `VITE_MAPTILER_KEY` (free tier) to upgrade to MapTiler vector styles. Click any point for a live **"This point"** dashboard (elevation now; slope/aspect/weather arrive in later phases).
  Terrain layers (Phase 2): hillshade, avalanche slope-angle shading, aspect, and on-the-fly contours, all from free elevation tiles (no key); clicking a point also reports slope° and aspect.
  Weather & hazard layers (Phase 3): live wildfire (FIRMS + WFIGS), air quality (AirNow), and avalanche danger zones (avalanche.org) fetched for the current map view; plus current weather, snow, and a freeze/thaw card on map click. Wildfire/AQI use the operator's free FIRMS/AirNow keys (graceful "needs key" otherwise); the rest are keyless.
- **GPX upload**: route drawn on map; bounding box used for fire/weather queries; length and elevation range computed.
- **Trip detail view**: full check history, manual notes, per-check flag/summary review.
- **Printable report**: `GET /trips/{id}/print-report` renders a standalone print-CSS page (also reachable from the UI) with every section, source table, checklist, and disclaimer.
- **Re-run all trips**: `POST /agent/run-all-saved-trips` re-checks all of your trips on demand. A staleness nudge prompts a re-check when any trip's last check is older than 12 hours.

## Architecture

```
/summit-signal
  /frontend            Vite + React + TypeScript + MapLibre GL
    /src/components    MapView, ConditionDashboard, TripForm, TripDetail, SettingsView, ...
    /src/lib/api.ts    typed REST client (reads VITE_API_BASE)
  /backend
    /app
      main.py          FastAPI app, lifespan seeding, CORS
      database.py      SQLAlchemy (SQLite for local dev, Postgres via DATABASE_URL)
      models.py        users, trips, locations, gpx_routes, condition_checks, connector_results,
                       risk_flags, ai_summaries, saved_reports, app_settings
      /connectors      one isolated, documented module per source; uniform
                       ConnectorOutput envelope; never raise, degrade to partial/failed/skipped
      /agent           jobs.py (threaded check pipeline), summarizer.py
      /services        risk_engine.py, gpx_parser.py, report_generator.py, settings_service.py
      /routes          trips.py, checks.py, misc.py
    /tests             offline pytest suite (run: python -m pytest tests/ -q)
```

Connectors share a `ConnectorContext` (point, dates, trip type, GPX bbox, settings, API keys) and return a normalized envelope, so any source can be swapped or extended (e.g., adding a region-specific avalanche API) without touching the pipeline.

## Configuration knobs (Settings UI)

Fire search radius · AQI moderate/major thresholds · wind-gust thresholds · precipitation-probability threshold · very-cold threshold · stale-data window · per-connector enable/disable.

## Deploying

### Frontend - Vercel

The repo includes `frontend/vercel.json`. Import the repo in Vercel, set the root to `frontend`, and add the environment variable:

- `VITE_API_BASE` - the full URL of your Render backend (e.g. `https://summitsignal-api.onrender.com`)

Vercel will run `npm run build` and serve `dist/`. The `rewrites` rule in `vercel.json` handles client-side routing.

### Backend - Render

The repo includes `backend/render.yaml`. Create a new Web Service in Render pointing at this repo; Render will detect the config automatically. Set the following environment variables in the Render dashboard:

| Variable | Description |
|---|---|
| `DATABASE_URL` | Postgres connection string from Neon (or any Postgres provider) |
| `JWT_SECRET` | A random string of at least 32 characters - used to sign auth tokens |
| `SIGNUP_CODE` | A shared invite code users must enter to create an account |
| `ALLOWED_ORIGINS` | Your Vercel frontend URL (e.g. `https://your-app.vercel.app`) |
| `SUMMIT_SIGNAL_FIRMS_KEY` | NASA FIRMS API key (free) |
| `SUMMIT_SIGNAL_AIRNOW_KEY` | AirNow API key (free) |
| `SUMMIT_SIGNAL_NPS_KEY` | NPS API key (free) |
| `SUMMIT_SIGNAL_ORS_KEY` | OpenRouteService API key (free) — enables route snapping. Optional; without it route building still works as manual, unsnapped routes. |
| `SUMMIT_SIGNAL_TRAILS_URL` | Optional comma-separated ArcGIS REST trail query URLs (no key) to fill OSM gaps in route snapping. Defaults to a public trail service. |

See `.env.example` at the repo root for the full list.

> **Note:** The Render free tier sleeps after inactivity. The first request after idle takes roughly 50 seconds (cold start). Paid tiers stay awake.

### Database - Neon (Postgres)

Create a Neon project, copy the connection string, and set it as `DATABASE_URL` on Render. On startup the backend calls `create_all`, which creates any missing tables. There is no Alembic migration system: `create_all` does not ALTER existing tables, so after a schema change you must drop and recreate the database (for local development, delete `backend/summit_signal.db`; for a fresh Postgres deploy this is a non-issue since the tables are created clean).

## Notes & limitations

- Forecast-area/avalanche-region map overlays are v1-minimal: fire detections and perimeters render on the map; NWS alert zones and avalanche zones are reported in the dashboard with source links.
- Elevation-adjusted temperatures are lapse-rate **estimates**, prominently labeled as such.
- No social media / forum scraping by design.
- Internet access is required at check time.
