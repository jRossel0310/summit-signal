# SummitSignal

A **local-first U.S. hiking, backpacking, and mountaineering trip-condition dashboard**. Pick a point on the map, save a trip, and run a real condition check against live government and public data sources. SummitSignal surfaces concern flags, data gaps, source links with timestamps, a manual verification checklist, an AI-assisted planning summary, and a printable report.

> **Disclaimer:** This tool highlights planning concerns from available sources. It does not determine whether a trip is safe. It never makes go/no-go decisions,   it only reports: *No major concerns found · Some concerns found · Major concerns found · Data incomplete · Source check failed.*

All data is stored locally in a SQLite file. No accounts, no cloud.

---

## Quick start (two commands)

Requires **Python 3.10+** and **Node 18+**.

**Terminal 1,   backend (port 8000):**

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Terminal 2,   frontend (port 5173):**

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The app seeds four sample trips on first run (Mount Rainier WA, Longs Peak CO, Yosemite Valley CA, Grand Canyon South Rim AZ). Select one and click **Run condition check**.

> Optional: use a Python virtual environment first (`python -m venv .venv && source .venv/bin/activate`).

---

## What a condition check does

A background job on the Python agent runs each connector in sequence, persisting every result as it lands (the UI polls progress live):

| Connector | Source | Key needed? |
|---|---|---|
| NWS Weather | api.weather.gov point → grid forecast, hourly, active alerts | no |
| USGS Elevation | EPQS (with Open-Meteo fallback, labeled) | no |
| Elevation-Adjusted Weather | Lapse-rate estimate (~3.5 °F/1000 ft) for trailhead/mid/high bands,   **clearly labeled estimate, not a forecast** | no |
| NASA FIRMS | VIIRS active fire detections, last 3 days, within your radius / GPX bounding box | yes (free) |
| NIFC/WFIGS | Current interagency fire perimeters; point-in-perimeter test | no |
| AirNow | Current AQI observations (labeled preliminary/unvalidated) | yes (free) |
| NPS Alerts | Alerts/closures for NPS units within ~35 mi; "not applicable" otherwise | yes (free) |
| Avalanche | avalanche.org zone lookup → links you to the proper forecast center. **No forecast scraping**,   manual check is always required for mountaineering/snowy terrain | no |
| Forecast Discussion | Latest NWS AFD for the responsible office, with keyword highlights (wind, snow, freezing level, severe, uncertainty…) | no |

The **risk engine** turns connector output into severity-tagged flags (info / moderate / major / unknown-data-gap) using thresholds you control in Settings, then computes the overall concern status and a data-completeness score. Missing keys, failed sources, and stale data are surfaced as explicit data-gap flags,   never silently ignored.

## API keys (all free)

Connectors that need keys are implemented and simply show **"API key needed"** until configured. Add keys in **Settings → API keys**, or via environment variables before starting the backend:

```bash
export SUMMIT_SIGNAL_FIRMS_KEY=...    # https://firms.modaps.eosdis.nasa.gov/api/map_key/
export SUMMIT_SIGNAL_AIRNOW_KEY=...   # https://docs.airnowapi.org/account/request/
export SUMMIT_SIGNAL_NPS_KEY=...      # https://www.nps.gov/subjects/developer/get-started.htm
```

Keys entered in the UI are stored only in the local SQLite database. Nothing is hardcoded.

## AI summaries

Two interchangeable summarizers:

1. **Rule-based** (default, always works),   builds a structured markdown summary strictly from connector results.
2. **Ollama** (optional),   enable in Settings, pick any locally installed model. The prompt is strictly grounded in connector output and instructed never to invent facts or make go/no-go statements. Any Ollama failure silently falls back to rule-based.

Every summary ends with the disclaimer and a manual verification checklist (avalanche forecast, permits, land-manager pages, re-check within 24 h of departure, etc.).

## Other features

- **Map** (MapLibre GL): OpenTopoMap/OSM basemaps, search by name or `lat, lon`, click-to-select, saved-trip markers, GPX route display, FIRMS detection dots, WFIGS perimeter polygons, per-layer toggles.
- **GPX upload**: route drawn on map; bounding box used for fire/weather queries; length and elevation range computed.
- **Trip detail view**: full check history, manual notes, per-check flag/summary review.
- **Printable report**: `GET /trips/{id}/print-report` renders a standalone print-CSS page (also reachable from the UI) with every section, source table, checklist, and disclaimer.
- **Agent**: `POST /agent/run-all-saved-trips`, plus an APScheduler background schedule (Settings → re-check every N hours).

## Architecture

```
/summit-signal
  /frontend            Vite + React + TypeScript + MapLibre GL
    /src/components    MapView, ConditionDashboard, TripForm, TripDetail, SettingsView, …
    /src/lib/api.ts    typed REST client (http://localhost:8000)
  /backend
    /app
      main.py          FastAPI app, lifespan seeding, CORS
      database.py      SQLite + SQLAlchemy (file: backend/summit_signal.db)
      models.py        trips, locations, gpx_routes, condition_checks, connector_results,
                       risk_flags, ai_summaries, saved_reports, app_settings, api_keys
      /connectors      one isolated, documented module per source; uniform
                       ConnectorOutput envelope; never raise, degrade to partial/failed/skipped
      /agent           jobs.py (threaded check pipeline), scheduler.py, summarizer.py, ollama_client.py
      /services        risk_engine.py, gpx_parser.py, report_generator.py, settings_service.py
      /routes          trips.py, checks.py, misc.py
    /tests             offline pytest suite (run: python -m pytest tests/ -q)
```

Connectors share a `ConnectorContext` (point, dates, trip type, GPX bbox, settings, API keys) and return a normalized envelope, so any source can be swapped or extended (e.g., adding a region-specific avalanche API) without touching the pipeline.

## Configuration knobs (Settings UI)

Fire search radius · AQI moderate/major thresholds · wind-gust thresholds · precipitation-probability threshold · very-cold threshold · stale-data window · per-connector enable/disable · Ollama URL/model · background schedule.

## Notes & limitations

- Forecast-area/avalanche-region map overlays are v1-minimal: fire detections and perimeters render on the map; NWS alert zones and avalanche zones are reported in the dashboard with source links.
- Elevation-adjusted temperatures are lapse-rate **estimates**, prominently labeled as such.
- No social media / forum scraping by design.
- Internet access is required at check time; the app itself runs entirely on your machine.
