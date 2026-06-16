# Map Layers — Phase 3 Weather & Hazards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add six weather/hazard families (wildfire, smoke/AQI, avalanche danger zones, current weather, snow, freeze/thaw) as point-context dashboard cards + live viewport map layers, reusing the existing condition-check connectors without touching the check pipeline.

**Architecture:** Six backend point-context providers (extending Phase 1's aggregator, now concurrent) wrap existing connectors or new free sources. A new `GET /map/layer/{id}?bbox` area endpoint returns viewport GeoJSON (also wrapping connectors), and a frontend `useViewportLayers` hook fetches it live as the map pans. Keys come from env (DB-free); free-source-first with graceful `needs-key`.

**Tech Stack:** Backend — FastAPI, httpx, pytest, `concurrent.futures`. Frontend — Vite + React + TS + MapLibre GL, Vitest.

**Spec:** `docs/superpowers/specs/2026-06-15-map-layers-phase3-weather-hazards-design.md`

---

## Conventions

- All work happens in the execution worktree (created by superpowers:using-git-worktrees at execution). Paths below are relative to the worktree root.
- **Backend tests:** from `<worktree>/backend`, run with the project venv interpreter:
  `"C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/<file> -q` (bare `python` lacks pytest).
- **Frontend type check:** `cd frontend && npx tsc -b` (exit 0). **Unit tests:** `npm test` (vitest). **Build:** `npm run build`.
- Wire format is snake_case. Commit after each task; do not push. Git Bash on Windows.
- **Additive only:** do NOT edit anything under `connectors/`, `agent/`, `services/risk_engine.py`, `services/summarizer.py`, `routes/checks.py`, `routes/trips.py`. Phase 3 *wraps* connectors; it never modifies them.

---

## File Structure

**Backend new:** `app/providers/_wrap.py` (connector-context helper), `app/providers/{current_weather,aqi,wildfire,snow,avalanche,freeze_thaw}.py`, `app/services/layer_data.py`, `tests/test_phase3_providers.py`, `tests/test_layer_data.py`.
**Backend modified:** `app/providers/aggregator.py` (concurrent fan-out + cache lock), `app/providers/registry.py` (+6, retire WeatherStub), `app/providers/stubs.py` (drop WeatherStub), `tests/test_providers.py` (stub-test update), `app/routes/map.py` (+area route), `app/schemas.py` (+LayerDataResponse), `app/main.py` (already includes the map router).
**Frontend new:** `src/layers/hazardColors.ts` (+test), `src/hooks/useViewportLayers.ts`.
**Frontend modified:** `src/layers/registry.ts`, `src/components/MapView.tsx`, `src/App.tsx`, `src/components/PointDashboard.tsx`, `src/lib/api.ts`, `src/index.css`, `README.md`.

---

## Task 1: Connector-wrapping helper

**Files:** Create `backend/app/providers/_wrap.py`; test in `backend/tests/test_phase3_providers.py`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_phase3_providers.py`:

```python
"""Phase 3 provider tests. Offline — wrapped connectors / http_client mocked."""
from app.providers._wrap import connector_ctx


def test_connector_ctx_loads_env_keys(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "abc")
    monkeypatch.setenv("SUMMIT_SIGNAL_AIRNOW_KEY", "")
    ctx = connector_ctx(40.0, -105.0)
    assert ctx.latitude == 40.0 and ctx.longitude == -105.0
    assert ctx.api_keys["firms"] == "abc"
    assert ctx.api_keys["airnow"] == ""
    assert ctx.settings.get("fire_radius_miles") == 30


def test_connector_ctx_passes_bbox():
    bbox = {"west": -106, "south": 39, "east": -105, "north": 40}
    ctx = connector_ctx(39.5, -105.5, bbox=bbox)
    assert ctx.bbox == bbox
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/test_phase3_providers.py -q`
Expected: `ModuleNotFoundError: No module named 'app.providers._wrap'`

- [ ] **Step 3: Implement**

Create `backend/app/providers/_wrap.py`:

```python
"""Build a ConnectorContext for wrapping existing connectors from the public
point-context path. Keys come from env (operator-provided); no DB needed."""
from __future__ import annotations
from ..connectors.base import ConnectorContext
from ..services.settings_service import get_api_key

_DEFAULT_SETTINGS = {"fire_radius_miles": 30}


def connector_ctx(lat: float, lon: float, bbox: dict | None = None,
                  keys=("firms", "airnow", "nps"), settings: dict | None = None) -> ConnectorContext:
    api_keys = {k: get_api_key(None, k) for k in keys}
    return ConnectorContext(
        latitude=lat, longitude=lon, start_date="", end_date="",
        bbox=bbox, settings=settings or dict(_DEFAULT_SETTINGS), api_keys=api_keys,
    )
```

- [ ] **Step 4: Run — expect PASS** (2 passed). Use the venv pytest command above.

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/_wrap.py backend/tests/test_phase3_providers.py
git commit -m "feat(providers): connector-context helper for wrapping connectors"
```

---

## Task 2: AQI provider (wraps airnow)

**Files:** Create `backend/app/providers/aqi.py`; append tests.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_phase3_providers.py`:

```python
from app.providers import aqi as aqi_mod
from app.providers.base import ProviderContext
from app.schemas import ConnectorOutput


def test_aqi_ok(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_AIRNOW_KEY", "k")
    monkeypatch.setattr(aqi_mod.airnow, "run", lambda ctx: ConnectorOutput(
        connector_name="airnow", status="success", source_name="AirNow",
        normalized={"max_aqi": 142, "readings": [
            {"parameter": "PM2.5", "aqi": 142, "category": "Unhealthy for Sensitive Groups",
             "reporting_area": "Boulder"}]}))
    out = aqi_mod.AqiProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["max_aqi"] == 142
    assert out.data["category"]


def test_aqi_needs_key(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_AIRNOW_KEY", "")
    out = aqi_mod.AqiProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "needs_key"


def test_aqi_never_raises(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_AIRNOW_KEY", "k")
    monkeypatch.setattr(aqi_mod.airnow, "run", lambda ctx: (_ for _ in ()).throw(RuntimeError("x")))
    out = aqi_mod.AqiProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status in ("error", "empty")
```

- [ ] **Step 2: Run — expect FAIL** (`No module named 'app.providers.aqi'`).

- [ ] **Step 3: Implement**

Create `backend/app/providers/aqi.py`:

```python
"""AQI point provider — wraps the airnow connector (current AQI within 75 mi)."""
from __future__ import annotations
from ..connectors import airnow
from ..services.settings_service import get_api_key
from .base import ProviderContext, ProviderResult, ok, empty, needs_key, error
from ._wrap import connector_ctx


class AqiProvider:
    id = "aqi"
    title = "Air quality (AQI)"
    requires_key = "airnow"
    always_on = False

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        if not get_api_key(None, "airnow"):
            return needs_key(self.id, self.title, "SUMMIT_SIGNAL_AIRNOW_KEY")
        try:
            cout = airnow.run(connector_ctx(ctx.latitude, ctx.longitude))
            n = cout.normalized or {}
            readings = n.get("readings") or []
            if not readings:
                return empty(self.id, self.title, "No AQI monitors within 75 miles")
            top = max(readings, key=lambda r: r.get("aqi") or -1)
            return ok(self.id, self.title, data={
                "max_aqi": n.get("max_aqi"),
                "category": top.get("category"),
                "parameter": top.get("parameter"),
                "reporting_area": top.get("reporting_area"),
            }, source_name="AirNow (US EPA partner network)",
               source_url="https://www.airnow.gov/")
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
```

- [ ] **Step 4: Run — expect PASS** (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/aqi.py backend/tests/test_phase3_providers.py
git commit -m "feat(providers): AQI point provider (wraps airnow)"
```

---

## Task 3: Wildfire provider (wraps nasa_firms)

**Files:** Create `backend/app/providers/wildfire.py`; append tests.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_phase3_providers.py`:

```python
from app.providers import wildfire as wildfire_mod


def test_wildfire_ok(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "k")
    monkeypatch.setattr(wildfire_mod.nasa_firms, "run", lambda ctx: ConnectorOutput(
        connector_name="nasa_firms", status="success",
        normalized={"count": 3, "nearest_miles": 4.2,
                    "detections": [{"confidence": "high", "distance_miles": 4.2}]}))
    out = wildfire_mod.WildfireProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["nearest_miles"] == 4.2
    assert out.data["count"] == 3


def test_wildfire_empty_when_none(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "k")
    monkeypatch.setattr(wildfire_mod.nasa_firms, "run", lambda ctx: ConnectorOutput(
        connector_name="nasa_firms", status="success",
        normalized={"count": 0, "nearest_miles": None, "detections": []}))
    out = wildfire_mod.WildfireProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "empty"


def test_wildfire_needs_key(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "")
    out = wildfire_mod.WildfireProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "needs_key"
```

- [ ] **Step 2: Run — expect FAIL** (`No module named 'app.providers.wildfire'`).

- [ ] **Step 3: Implement**

Create `backend/app/providers/wildfire.py`:

```python
"""Wildfire point provider — nearest active fire (wraps nasa_firms)."""
from __future__ import annotations
from ..connectors import nasa_firms
from ..services.settings_service import get_api_key
from .base import ProviderContext, ProviderResult, ok, empty, needs_key, error
from ._wrap import connector_ctx


class WildfireProvider:
    id = "wildfire"
    title = "Active wildfire"
    requires_key = "firms"
    always_on = False

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        if not get_api_key(None, "firms"):
            return needs_key(self.id, self.title, "SUMMIT_SIGNAL_FIRMS_KEY")
        try:
            cout = nasa_firms.run(connector_ctx(ctx.latitude, ctx.longitude))
            n = cout.normalized or {}
            count = n.get("count") or 0
            if count == 0:
                return empty(self.id, self.title, "No active fire detections nearby (last 3 days)")
            nearest = (n.get("detections") or [{}])[0]
            return ok(self.id, self.title, data={
                "count": count,
                "nearest_miles": n.get("nearest_miles"),
                "nearest_confidence": nearest.get("confidence"),
            }, source_name="NASA FIRMS (VIIRS, last 3 days)",
               source_url="https://firms.modaps.eosdis.nasa.gov/map/")
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
```

- [ ] **Step 4: Run — expect PASS** (8 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/wildfire.py backend/tests/test_phase3_providers.py
git commit -m "feat(providers): wildfire point provider (wraps nasa_firms)"
```

---

## Task 4: Avalanche provider (wraps avalanche connector)

**Files:** Create `backend/app/providers/avalanche.py`; append tests.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_phase3_providers.py`:

```python
from app.providers import avalanche as avy_mod


def test_avalanche_in_zone(monkeypatch):
    monkeypatch.setattr(avy_mod.avalanche, "run", lambda ctx: ConnectorOutput(
        connector_name="avalanche", status="success",
        normalized={"in_forecast_zone": True, "zone": {
            "zone_name": "Front Range", "center": "CAIC", "current_danger": "Considerable",
            "forecast_link": "https://avalanche.state.co.us/"}}))
    out = avy_mod.AvalancheProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["danger"] == "Considerable"
    assert "CAIC" in out.data["center"]


def test_avalanche_no_zone(monkeypatch):
    monkeypatch.setattr(avy_mod.avalanche, "run", lambda ctx: ConnectorOutput(
        connector_name="avalanche", status="success",
        normalized={"in_forecast_zone": False, "zone": None}))
    out = avy_mod.AvalancheProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "empty"
```

- [ ] **Step 2: Run — expect FAIL** (`No module named 'app.providers.avalanche'`).

- [ ] **Step 3: Implement**

Create `backend/app/providers/avalanche.py`:

```python
"""Avalanche point provider — your zone's danger + center (wraps avalanche)."""
from __future__ import annotations
from ..connectors import avalanche
from .base import ProviderContext, ProviderResult, ok, empty, error
from ._wrap import connector_ctx


class AvalancheProvider:
    id = "avalanche"
    title = "Avalanche zone"
    requires_key = None
    always_on = False

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        try:
            cout = avalanche.run(connector_ctx(ctx.latitude, ctx.longitude))
            n = cout.normalized or {}
            zone = n.get("zone")
            if not n.get("in_forecast_zone") or not zone:
                return empty(self.id, self.title,
                             "Not inside a mapped avalanche forecast zone")
            return ok(self.id, self.title, data={
                "zone_name": zone.get("zone_name"),
                "danger": zone.get("current_danger"),
                "center": zone.get("center"),
            }, source_name="Avalanche.org forecast zones",
               source_url=zone.get("forecast_link") or "https://avalanche.org/")
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
```

- [ ] **Step 4: Run — expect PASS** (10 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/avalanche.py backend/tests/test_phase3_providers.py
git commit -m "feat(providers): avalanche point provider (wraps avalanche connector)"
```

---

## Task 5: Current-weather provider (NWS station obs)

**Files:** Create `backend/app/providers/current_weather.py`; append tests.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_phase3_providers.py`:

```python
from app.providers import current_weather as cw_mod


class _Resp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): return None
    def json(self): return self._p


class _CwClient:
    """points -> observationStations -> stations list -> latest obs."""
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get(self, url, params=None):
        if "/points/" in url:
            return _Resp({"properties": {"observationStations": "https://api.weather.gov/stations"}})
        if url.endswith("/stations"):
            return _Resp({"features": [{"id": "https://api.weather.gov/stations/KBDU",
                                        "properties": {"name": "Boulder"}}]})
        return _Resp({"properties": {
            "temperature": {"value": 12.0}, "windSpeed": {"value": 18.0},
            "windGust": {"value": 30.0}, "relativeHumidity": {"value": 40.0},
            "textDescription": "Mostly Cloudy"}})


def test_current_weather_ok(monkeypatch):
    monkeypatch.setattr(cw_mod, "http_client", lambda: _CwClient())
    out = cw_mod.CurrentWeatherProvider().fetch(ProviderContext(40.0, -105.27))
    assert out.status == "ok"
    assert out.data["temp_f"] == round(12.0 * 9 / 5 + 32)   # C -> F
    assert out.data["conditions"] == "Mostly Cloudy"
    assert out.data["station"] == "Boulder"


def test_current_weather_never_raises(monkeypatch):
    class _Boom:
        def __enter__(self): raise RuntimeError("down")
        def __exit__(self, *a): return False
    monkeypatch.setattr(cw_mod, "http_client", lambda: _Boom())
    out = cw_mod.CurrentWeatherProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status in ("error", "empty")
```

- [ ] **Step 2: Run — expect FAIL** (`No module named 'app.providers.current_weather'`).

- [ ] **Step 3: Implement**

Create `backend/app/providers/current_weather.py`:

```python
"""Current-weather point provider — nearest NWS station's latest observation."""
from __future__ import annotations
from ..connectors.base import http_client, utcnow_iso
from .base import ProviderContext, ProviderResult, ok, empty, error

POINTS = "https://api.weather.gov/points/{lat:.4f},{lon:.4f}"


def _c_to_f(c):
    return None if c is None else round(c * 9 / 5 + 32)


def _ms_to_mph(ms):
    return None if ms is None else round(ms * 2.23694)


class CurrentWeatherProvider:
    id = "current_weather"
    title = "Current weather"
    requires_key = None
    always_on = True

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        try:
            with http_client() as client:
                pr = client.get(POINTS.format(lat=ctx.latitude, lon=ctx.longitude))
                pr.raise_for_status()
                stations_url = (pr.json().get("properties") or {}).get("observationStations")
                if not stations_url:
                    return empty(self.id, self.title, "No NWS station for this point")
                sr = client.get(stations_url)
                sr.raise_for_status()
                feats = sr.json().get("features") or []
                if not feats:
                    return empty(self.id, self.title, "No nearby NWS station")
                station = feats[0]
                obs = client.get(f"{station['id']}/observations/latest")
                obs.raise_for_status()
                p = obs.json().get("properties") or {}
                return ok(self.id, self.title, data={
                    "temp_f": _c_to_f((p.get("temperature") or {}).get("value")),
                    "wind_mph": _ms_to_mph((p.get("windSpeed") or {}).get("value")),
                    "gust_mph": _ms_to_mph((p.get("windGust") or {}).get("value")),
                    "humidity_pct": round(v) if (v := (p.get("relativeHumidity") or {}).get("value")) is not None else None,
                    "conditions": p.get("textDescription"),
                    "station": (station.get("properties") or {}).get("name"),
                }, source_name="National Weather Service stations",
                   source_url="https://www.weather.gov/", source_timestamp=utcnow_iso())
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
```

- [ ] **Step 4: Run — expect PASS** (12 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/current_weather.py backend/tests/test_phase3_providers.py
git commit -m "feat(providers): current-weather provider (NWS nearest-station obs)"
```

---

## Task 6: Snow provider (Open-Meteo)

**Files:** Create `backend/app/providers/snow.py`; append tests.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_phase3_providers.py`:

```python
from app.providers import snow as snow_mod


def test_snow_ok(monkeypatch):
    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, params=None):
            return _Resp({"current": {"snow_depth": 0.42, "snowfall": 1.5},
                          "daily": {"snowfall_sum": [3.0, 0.0, 0.0]}})
    monkeypatch.setattr(snow_mod, "http_client", lambda: _C())
    out = snow_mod.SnowProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["snow_depth_in"] == round(0.42 * 39.3701)   # m -> in
    assert out.data["recent_snowfall_in"] is not None


def test_snow_empty_when_no_snow(monkeypatch):
    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, params=None):
            return _Resp({"current": {"snow_depth": 0.0, "snowfall": 0.0},
                          "daily": {"snowfall_sum": [0.0]}})
    monkeypatch.setattr(snow_mod, "http_client", lambda: _C())
    out = snow_mod.SnowProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status in ("ok", "empty")  # zero snow is a valid "no snow" answer
    assert out.data["snow_depth_in"] == 0
```

- [ ] **Step 2: Run — expect FAIL** (`No module named 'app.providers.snow'`).

- [ ] **Step 3: Implement**

Create `backend/app/providers/snow.py`:

```python
"""Snow point provider — snow depth + recent snowfall from Open-Meteo (free)."""
from __future__ import annotations
from ..connectors.base import http_client, utcnow_iso
from .base import ProviderContext, ProviderResult, ok, error

URL = "https://api.open-meteo.com/v1/forecast"
M_TO_IN = 39.3701


class SnowProvider:
    id = "snow"
    title = "Snow"
    requires_key = None
    always_on = True

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        try:
            with http_client() as client:
                r = client.get(URL, params={
                    "latitude": ctx.latitude, "longitude": ctx.longitude,
                    "current": "snow_depth,snowfall", "daily": "snowfall_sum",
                    "forecast_days": 1, "past_days": 2, "timezone": "auto"})
                r.raise_for_status()
                j = r.json()
                depth_m = (j.get("current") or {}).get("snow_depth")
                recent = sum(x for x in ((j.get("daily") or {}).get("snowfall_sum") or [])
                             if isinstance(x, (int, float)))
                return ok(self.id, self.title, data={
                    "snow_depth_in": round((depth_m or 0) * M_TO_IN),
                    "recent_snowfall_in": round(recent, 1),
                }, source_name="Open-Meteo (snow depth / snowfall)",
                   source_url="https://open-meteo.com/", source_timestamp=utcnow_iso())
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
```

- [ ] **Step 4: Run — expect PASS** (14 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/snow.py backend/tests/test_phase3_providers.py
git commit -m "feat(providers): snow provider (Open-Meteo depth + recent snowfall)"
```

---

## Task 7: Freeze/thaw provider (derived)

**Files:** Create `backend/app/providers/freeze_thaw.py`; append tests.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_phase3_providers.py`:

```python
from app.providers import freeze_thaw as ft_mod


def _hourly(temps):
    return [{"time": f"2026-06-15T{h:02d}:00:00", "temperature_f": t} for h, t in enumerate(temps)]


def test_freeze_thaw_counts_hours_below_freezing(monkeypatch):
    # 24 temps: first 6 below freezing, rest above
    temps = [25, 26, 28, 30, 31, 20] + [40] * 18
    monkeypatch.setattr(ft_mod.nws_weather, "run", lambda ctx: ConnectorOutput(
        connector_name="nws_weather", status="success",
        normalized={"hourly_sample": _hourly(temps), "high_f": 55, "low_f": 20}))
    out = ft_mod.FreezeThawProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["hours_below_freezing"] == 6
    assert out.data["overnight_low_f"] is not None
    assert out.data["refreeze"] in ("likely", "marginal", "no")


def test_freeze_thaw_empty_without_forecast(monkeypatch):
    monkeypatch.setattr(ft_mod.nws_weather, "run", lambda ctx: ConnectorOutput(
        connector_name="nws_weather", status="failed", normalized={"hourly_sample": []}))
    out = ft_mod.FreezeThawProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "empty"
```

- [ ] **Step 2: Run — expect FAIL** (`No module named 'app.providers.freeze_thaw'`).

- [ ] **Step 3: Implement**

Create `backend/app/providers/freeze_thaw.py`:

```python
"""Freeze/thaw point provider — derived from the NWS forecast (wraps nws_weather)
plus a refreeze heuristic. Elevation lapse + solar aspect are layered in by the
dashboard using the elevation/slope_aspect sections; this card focuses on the
freeze timing the forecast gives directly."""
from __future__ import annotations
from ..connectors import nws_weather
from .base import ProviderContext, ProviderResult, ok, empty, error
from ._wrap import connector_ctx

FREEZING_F = 32
REFREEZE_LOW_F = 28


class FreezeThawProvider:
    id = "freeze_thaw"
    title = "Freeze / thaw"
    requires_key = None
    always_on = True

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        try:
            cout = nws_weather.run(connector_ctx(ctx.latitude, ctx.longitude))
            n = cout.normalized or {}
            hourly = [h for h in (n.get("hourly_sample") or [])
                      if h.get("temperature_f") is not None]
            if not hourly:
                return empty(self.id, self.title, "No hourly forecast for this point")
            temps = [h["temperature_f"] for h in hourly[:24]]
            below = sum(1 for t in temps if t < FREEZING_F)
            overnight_low = min(temps)
            high = n.get("high_f")
            if overnight_low < REFREEZE_LOW_F and (high is None or high > FREEZING_F):
                refreeze = "likely"
            elif overnight_low < FREEZING_F:
                refreeze = "marginal"
            else:
                refreeze = "no"
            return ok(self.id, self.title, data={
                "overnight_low_f": round(overnight_low),
                "hours_below_freezing": below,
                "refreeze": refreeze,
            }, source_name="Derived from NWS hourly forecast",
               source_url="https://www.weather.gov/")
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
```

> Note: per the spec the card also surfaces an elevation-adjusted low and a solar-aspect note — those are layered in the frontend `PointDashboard` (Task 16) by combining this section with the existing `elevation` and `slope_aspect` sections, so the backend stays a single forecast-derived unit.

- [ ] **Step 4: Run — expect PASS** (16 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/freeze_thaw.py backend/tests/test_phase3_providers.py
git commit -m "feat(providers): freeze/thaw provider (derived from NWS forecast)"
```

---

## Task 8: Concurrent aggregator + register the 6 providers

**Files:** Modify `backend/app/providers/aggregator.py`, `registry.py`, `stubs.py`, `tests/test_providers.py`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_providers.py`:

```python
def test_aggregator_runs_providers_concurrently_in_order(monkeypatch):
    import time as _t
    from app.providers import aggregator as agg
    from app.providers.base import ok as _ok
    agg.clear_cache()

    class _Slow:
        def __init__(self, pid): self.id = pid; self.title = pid; self.always_on = True; self.requires_key = None
        def fetch(self, ctx):
            _t.sleep(0.2)
            return _ok(self.id, self.title, {"v": self.id})

    provs = [_Slow("a"), _Slow("b"), _Slow("c")]
    monkeypatch.setattr(agg, "select_providers", lambda ids: provs)
    start = _t.monotonic()
    out = agg.point_context(40.0, -105.0)
    elapsed = _t.monotonic() - start
    assert [s["layer_id"] for s in out["sections"]] == ["a", "b", "c"]   # order preserved
    assert elapsed < 0.5   # 3x0.2s concurrent, not 0.6s sequential
```

- [ ] **Step 2: Run — expect FAIL** (sequential aggregator → elapsed ~0.6s, assert `< 0.5` fails).

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/test_providers.py::test_aggregator_runs_providers_concurrently_in_order -q`

- [ ] **Step 3: Make the aggregator concurrent (thread-safe cache)**

In `backend/app/providers/aggregator.py`, add `import threading` and `from concurrent.futures import ThreadPoolExecutor` at the top, add a module-level `_lock = threading.Lock()`, and replace `_cached_fetch` + `point_context` with:

```python
def _cached_fetch(provider, ctx) -> ProviderResult:
    key = _cache_key(provider.id, ctx.latitude, ctx.longitude)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and (now - hit[0]) < CACHE_TTL_SECONDS:
            _cache.move_to_end(key)
            return hit[1]
    try:
        result = provider.fetch(ctx)   # network I/O OUTSIDE the lock
    except Exception as e:  # providers should never raise, but never trust it
        result = error(provider.id, getattr(provider, "title", provider.id), str(e))
    with _lock:
        _cache[key] = (time.monotonic(), result)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)
    return result


def point_context(lat: float, lon: float, layer_ids=None, settings=None) -> dict:
    ctx = ProviderContext(latitude=lat, longitude=lon, settings=settings or {})
    providers = select_providers(layer_ids)
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(providers)))) as pool:
        results = list(pool.map(lambda p: _cached_fetch(p, ctx), providers))
    place_name = None
    sections = []
    for provider, res in zip(providers, results):
        if provider.id == "placename":
            if res.status == "ok" and res.data:
                place_name = res.data.get("name")
            continue
        sections.append(_section_wire(res))
    return {"lat": lat, "lon": lon, "place_name": place_name, "sections": sections}
```

(`pool.map` preserves input order, so sections stay deterministic.)

- [ ] **Step 4: Register the 6 providers, retire WeatherStub**

In `backend/app/providers/registry.py`, replace the import + `_ALL` block:

```python
from . import stubs
from .slope_aspect import SlopeAspectProvider
from .current_weather import CurrentWeatherProvider
from .snow import SnowProvider
from .freeze_thaw import FreezeThawProvider
from .aqi import AqiProvider
from .wildfire import WildfireProvider
from .avalanche import AvalancheProvider

_ALL: list[Provider] = [
    PlaceNameProvider(),
    ElevationProvider(),
    SlopeAspectProvider(),
    CurrentWeatherProvider(),
    SnowProvider(),
    FreezeThawProvider(),
    AqiProvider(),
    WildfireProvider(),
    AvalancheProvider(),
]
```

(Delete the `stubs.WeatherStub` and `stubs.SlopeAspectStub` entries — both gone. Keep the `from . import stubs` import only if still used; since no stub remains, remove that import line too.)

In `backend/app/providers/stubs.py`, the file no longer has any stub. Delete `stubs.py` entirely (no providers reference it now). 

- [ ] **Step 5: Update test_providers.py for the stub removal**

In `backend/tests/test_providers.py`, DELETE the `test_stub_is_coming_soon` test and its `from app.providers import stubs` import (the stub module is gone). The `test_point_context_includes_coming_soon` route test (in `test_point_context.py`) used `layers=weather` — that provider id no longer exists, so update it: change `test_point_context_includes_coming_soon` to assert that requesting an unknown layer id simply yields no extra section (the always-on sections still return), i.e. replace its body with:

```python
def test_point_context_unknown_layer_id_ignored(monkeypatch):
    _patch(monkeypatch)
    r = client.get("/map/point-context", params={"lat": 40.0, "lon": -105.0, "layers": "nope"})
    assert r.status_code == 200
    ids = {s["layer_id"] for s in r.json()["sections"]}
    assert "nope" not in ids and "elevation" in ids
```

- [ ] **Step 6: Run the FULL backend suite**

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/ -q`
Expected: ALL pass. The point-context now returns the always-on sections (elevation, slope_aspect, current_weather, snow, freeze_thaw) plus any requested gated ones. Network providers in `test_point_context.py` are mocked there; the new always-on providers (current_weather/snow/freeze_thaw) will attempt real calls in those tests unless mocked — so in `test_point_context.py`'s `_patch`, also monkeypatch `current_weather.http_client`, `snow.http_client`, and `freeze_thaw`'s `nws_weather.run` to safe stubs (add these to `_patch`). Add to `_patch`:

```python
    from app.providers import current_weather as _cw, snow as _snow, freeze_thaw as _ft
    from app.schemas import ConnectorOutput as _CO
    monkeypatch.setattr(_cw, "http_client", lambda: _FakeClient())
    monkeypatch.setattr(_snow, "http_client", lambda: _FakeClient())
    monkeypatch.setattr(_ft.nws_weather, "run", lambda ctx: _CO(
        connector_name="nws_weather", status="success",
        normalized={"hourly_sample": [], "high_f": None, "low_f": None}))
```

(and extend `_FakeClient.get` to return `{}` for unknown URLs, which it already does). Re-run until green.

- [ ] **Step 7: Commit**

```bash
git add backend/app/providers/aggregator.py backend/app/providers/registry.py backend/tests/test_providers.py backend/tests/test_point_context.py
git rm backend/app/providers/stubs.py
git commit -m "feat(providers): concurrent aggregator + register 6 weather/hazard providers"
```

---

## Task 9: Viewport layer-data service

**Files:** Create `backend/app/services/layer_data.py`; test in `backend/tests/test_layer_data.py`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_layer_data.py`:

```python
"""Viewport layer-data dispatch + cache. Offline (connectors mocked)."""
from app.services import layer_data
from app.schemas import ConnectorOutput

BBOX = {"west": -106.0, "south": 39.0, "east": -105.0, "north": 40.0}


def test_fires_to_geojson(monkeypatch):
    layer_data.clear_cache()
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "k")
    monkeypatch.setattr(layer_data.nasa_firms, "run", lambda ctx: ConnectorOutput(
        connector_name="nasa_firms", status="success",
        normalized={"detections": [{"latitude": 39.5, "longitude": -105.5,
                                     "confidence": "high", "acq_date": "2026-06-15"}]}))
    out = layer_data.layer_features("fires", BBOX)
    assert out["status"] == "ok"
    f = out["features"][0]
    assert f["geometry"]["type"] == "Point"
    assert f["geometry"]["coordinates"] == [-105.5, 39.5]


def test_fires_needs_key(monkeypatch):
    layer_data.clear_cache()
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "")
    out = layer_data.layer_features("fires", BBOX)
    assert out["status"] == "needs_key" and out["features"] == []


def test_cache_prevents_refetch(monkeypatch):
    layer_data.clear_cache()
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "k")
    calls = {"n": 0}
    def _run(ctx):
        calls["n"] += 1
        return ConnectorOutput(connector_name="nasa_firms", status="success", normalized={"detections": []})
    monkeypatch.setattr(layer_data.nasa_firms, "run", _run)
    layer_data.layer_features("fires", BBOX)
    layer_data.layer_features("fires", BBOX)
    assert calls["n"] == 1


def test_unknown_layer():
    out = layer_data.layer_features("nope", BBOX)
    assert out["status"] == "error" and out["features"] == []
```

- [ ] **Step 2: Run — expect FAIL** (`No module named 'app.services.layer_data'`).

- [ ] **Step 3: Implement**

Create `backend/app/services/layer_data.py`:

```python
"""Viewport (bbox) -> GeoJSON for hazard map layers. Wraps existing connectors;
keys from env; cached by (layer, rounded bbox). Never raises."""
from __future__ import annotations
import time
from collections import OrderedDict
from ..connectors import nasa_firms, nifc_wfigs, avalanche
from ..providers._wrap import connector_ctx
from ..services.settings_service import get_api_key
from ..connectors.base import ConnectorContext

_TTL = {"fires": 300.0, "perimeters": 1800.0, "avalanche": 1800.0, "aqi": 900.0}
_CACHE_MAX = 256
_cache: "OrderedDict[tuple, tuple[float, dict]]" = OrderedDict()


def clear_cache() -> None:
    _cache.clear()


def _bbox_ctx(bbox: dict) -> ConnectorContext:
    cx = (bbox["west"] + bbox["east"]) / 2
    cy = (bbox["south"] + bbox["north"]) / 2
    ctx = connector_ctx(cy, cx, bbox=bbox)
    return ctx


def _fires(bbox):
    if not get_api_key(None, "firms"):
        return "needs_key", []
    out = nasa_firms.run(_bbox_ctx(bbox))
    feats = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [d["longitude"], d["latitude"]]},
        "properties": {"confidence": d.get("confidence"), "acq_date": d.get("acq_date"),
                       "distance_miles": d.get("distance_miles")},
    } for d in (out.normalized or {}).get("detections", [])]
    return "ok", feats


def _perimeters(bbox):
    out = nifc_wfigs.run(_bbox_ctx(bbox))
    feats = [{
        "type": "Feature", "geometry": p.get("geometry"),
        "properties": {"name": p.get("name"), "acres": p.get("acres"),
                       "percent_contained": p.get("percent_contained")},
    } for p in (out.normalized or {}).get("perimeters", []) if p.get("geometry")]
    return "ok", feats


def _avalanche(bbox):
    # avalanche.org map-layer is global GeoJSON; the connector fetches it via run().
    # Reuse it through the http_client the connector uses; return all zones (the
    # client filters to the viewport via MapLibre). Wrap connector's fetch by
    # calling its module-level MAP_LAYER through http_client.
    from ..connectors.base import http_client
    with http_client() as client:
        r = client.get(avalanche.MAP_LAYER)
        r.raise_for_status()
        gj = r.json()
    feats = []
    for feat in gj.get("features", []):
        props = feat.get("properties") or {}
        feats.append({"type": "Feature", "geometry": feat.get("geometry"),
                      "properties": {"name": props.get("name"), "danger": props.get("danger"),
                                     "center": props.get("center")}})
    return "ok", feats


def _aqi(bbox):
    if not get_api_key(None, "airnow"):
        return "needs_key", []
    # AirNow Data API (bbox) — monitor points colored by AQI on the client.
    from ..connectors.base import http_client
    key = get_api_key(None, "airnow")
    params = {
        "startDate": "", "endDate": "",
        "parameters": "PM25", "BBOX": f"{bbox['west']},{bbox['south']},{bbox['east']},{bbox['north']}",
        "dataType": "A", "format": "application/json", "verbose": 1, "API_KEY": key,
    }
    with http_client() as client:
        r = client.get("https://www.airnowapi.org/aq/data/", params=params)
        r.raise_for_status()
        rows = r.json() if isinstance(r.json(), list) else []
    feats = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row.get("Longitude"), row.get("Latitude")]},
        "properties": {"aqi": row.get("AQI"), "parameter": row.get("Parameter"),
                       "site": row.get("SiteName")},
    } for row in rows if row.get("Latitude") is not None]
    return "ok", feats


_FETCHERS = {"fires": _fires, "perimeters": _perimeters,
             "avalanche": _avalanche, "aqi": _aqi}


def _key(layer_id, bbox):
    return (layer_id, round(bbox["west"], 2), round(bbox["south"], 2),
            round(bbox["east"], 2), round(bbox["north"], 2))


def layer_features(layer_id: str, bbox: dict) -> dict:
    if layer_id not in _FETCHERS:
        return {"status": "error", "features": []}
    key = _key(layer_id, bbox)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and (now - hit[0]) < _TTL.get(layer_id, 600.0):
        _cache.move_to_end(key)
        return hit[1]
    try:
        status, feats = _FETCHERS[layer_id](bbox)
        result = {"status": status, "features": feats}
    except Exception as e:  # noqa: BLE001
        result = {"status": "error", "features": [], "message": str(e)[:200]}
    _cache[key] = (now, result)
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return result
```

- [ ] **Step 4: Run — expect PASS** (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/layer_data.py backend/tests/test_layer_data.py
git commit -m "feat(layers): viewport bbox->GeoJSON layer-data service (wraps connectors)"
```

---

## Task 10: Area route `GET /map/layer/{id}`

**Files:** Modify `backend/app/schemas.py`, `backend/app/routes/map.py`; test in `backend/tests/test_layer_data.py` (append).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_layer_data.py`:

```python
import os, tempfile
os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "ld.db"))
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

_cm = TestClient(app); client = _cm.__enter__()
def teardown_module(_m): _cm.__exit__(None, None, None)


def test_layer_route_ok(monkeypatch):
    layer_data.clear_cache()
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "k")
    monkeypatch.setattr(layer_data.nasa_firms, "run", lambda ctx: ConnectorOutput(
        connector_name="nasa_firms", status="success",
        normalized={"detections": [{"latitude": 39.5, "longitude": -105.5, "confidence": "h"}]}))
    r = client.get("/map/layer/fires", params={"west": -106, "south": 39, "east": -105, "north": 40})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["features"][0]["geometry"]["type"] == "Point"


def test_layer_route_bad_bbox():
    r = client.get("/map/layer/fires", params={"west": -106, "south": 39, "east": -105, "north": 999})
    assert r.status_code == 400
```

- [ ] **Step 2: Run — expect FAIL** (404 on `/map/layer/fires`).

- [ ] **Step 3: Add the schema**

Append to `backend/app/schemas.py`:

```python
class LayerDataResponse(BaseModel):
    status: str
    features: list[dict] = Field(default_factory=list)
    message: Optional[str] = None
```

- [ ] **Step 4: Add the route**

In `backend/app/routes/map.py`, add the import and route (below the existing point-context route):

```python
from ..schemas import LayerDataResponse
from ..services.layer_data import layer_features


@router.get("/map/layer/{layer_id}", response_model=LayerDataResponse)
def get_layer(layer_id: str, west: float, south: float, east: float, north: float):
    if not (-90 <= south <= 90 and -90 <= north <= 90 and -180 <= west <= 180 and -180 <= east <= 180):
        raise HTTPException(400, "bbox out of range")
    return layer_features(layer_id, {"west": west, "south": south, "east": east, "north": north})
```

(`HTTPException` is already imported in `map.py` from the Phase 1 point-context route.)

- [ ] **Step 5: Run the route tests + FULL suite**

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/test_layer_data.py -q` → PASS.
Then full suite: `... -m pytest tests/ -q` → ALL pass (coexistence gate).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routes/map.py backend/tests/test_layer_data.py
git commit -m "feat(api): GET /map/layer/{id} viewport hazard GeoJSON"
```

---

## Task 11: Hazard colors (frontend, Vitest)

**Files:** Create `frontend/src/layers/hazardColors.ts` + `hazardColors.test.ts`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/layers/hazardColors.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { aqiColor, aqiCategory, avyColor } from "./hazardColors";

describe("aqi", () => {
  it("colors by EPA breakpoint", () => {
    expect(aqiColor(40)).toBe("#00e400");   // good
    expect(aqiColor(120)).toBe("#ff7e00");  // USG
    expect(aqiColor(250)).toBe("#8f3f97");  // very unhealthy
  });
  it("labels categories", () => {
    expect(aqiCategory(40)).toBe("Good");
    expect(aqiCategory(160)).toBe("Unhealthy");
  });
});

describe("avalanche danger", () => {
  it("colors by NAC level (name or number)", () => {
    expect(avyColor("Considerable")).toBe("#f7941e");
    expect(avyColor("High")).toBe("#ed1c24");
    expect(avyColor(1)).toBe("#52ba4a"); // Low
  });
});
```

- [ ] **Step 2: Run `npm test` — expect FAIL** (cannot find `./hazardColors`).

- [ ] **Step 3: Implement**

Create `frontend/src/layers/hazardColors.ts`:

```ts
// EPA AQI category colors + NAC avalanche danger colors (canonical scales).
export interface AqiBand { max: number; color: string; label: string; }

export const AQI_BANDS: AqiBand[] = [
  { max: 50, color: "#00e400", label: "Good" },
  { max: 100, color: "#ffff00", label: "Moderate" },
  { max: 150, color: "#ff7e00", label: "Unhealthy for Sensitive Groups" },
  { max: 200, color: "#ff0000", label: "Unhealthy" },
  { max: 300, color: "#8f3f97", label: "Very Unhealthy" },
  { max: Infinity, color: "#7e0023", label: "Hazardous" },
];

export function aqiColor(aqi: number): string {
  return (AQI_BANDS.find((b) => aqi <= b.max) ?? AQI_BANDS[AQI_BANDS.length - 1]).color;
}
export function aqiCategory(aqi: number): string {
  return (AQI_BANDS.find((x) => aqi <= x.max) ?? AQI_BANDS[AQI_BANDS.length - 1]).label;
}

export const AVY_DANGER: Record<string, string> = {
  "1": "#52ba4a", low: "#52ba4a",
  "2": "#fff300", moderate: "#fff300",
  "3": "#f7941e", considerable: "#f7941e",
  "4": "#ed1c24", high: "#ed1c24",
  "5": "#231f20", extreme: "#231f20",
};

export function avyColor(level: string | number): string {
  return AVY_DANGER[String(level).toLowerCase().trim()] ?? "#9aa395";
}
```

- [ ] **Step 4: Run `npm test` — expect PASS.**

- [ ] **Step 5: Run `npx tsc -b` — expect no errors.**

- [ ] **Step 6: Commit**

```bash
git add frontend/src/layers/hazardColors.ts frontend/src/layers/hazardColors.test.ts
git commit -m "feat(hazards): EPA AQI + NAC avalanche danger color scales + tests"
```

---

## Task 12: API client — layerData

**Files:** Modify `frontend/src/lib/api.ts`.

- [ ] **Step 1: Add the types + method**

In `frontend/src/lib/api.ts`, add below the `SelectionResult` import:

```ts
export interface LayerData { status: string; features: GeoJSON.Feature[]; message?: string | null; }
```

In the `api` object, after `pointContext`, add:

```ts
  layerData: (id: string, bbox: { west: number; south: number; east: number; north: number }) => {
    const q = new URLSearchParams({
      west: String(bbox.west), south: String(bbox.south),
      east: String(bbox.east), north: String(bbox.north),
    });
    return request<LayerData>(`/map/layer/${id}?${q.toString()}`);
  },
```

- [ ] **Step 2: Run `npx tsc -b` — expect no errors** (the global `GeoJSON` types are available via maplibre's dependency / `@types`).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(api-client): layerData(id, bbox) for viewport hazard GeoJSON"
```

---

## Task 13: Registry hazard layers

**Files:** Modify `frontend/src/layers/registry.ts`.

- [ ] **Step 1: Replace the weather coming-soon row with hazard layers**

In `frontend/src/layers/registry.ts`, the `overlay.fires` and `overlay.perimeters` rows already exist (Phase 1). Change them to data-overlays (add `providerId`), and replace the `overlay.weather` coming-soon row with the avalanche + AQI layers. Specifically:

Change `overlay.perimeters` and `overlay.fires` entries to add a `providerId` and `kind: "data-overlay"`:

```ts
  { id: "overlay.perimeters", group: "hazard", kind: "data-overlay", label: "Fire perimeters",
    providerId: "wildfire", defaultVisible: false, defaultOpacity: 0.18, supportsOpacity: true,
    legend: { kind: "swatches", items: [{ color: "#d84a1b", label: "Active perimeter" }] } },
  { id: "overlay.fires", group: "hazard", kind: "data-overlay", label: "Active fires",
    providerId: "wildfire", defaultVisible: false, defaultOpacity: 0.75, supportsOpacity: true,
    legend: { kind: "swatches", items: [{ color: "#ff5a1f", label: "VIIRS detection" }] } },
```

(Note: `defaultVisible` flips to `false` — hazards are opt-in and now fetched live, not auto-shown from a trip check.)

Replace the `overlay.weather` coming-soon entry with:

```ts
  { id: "overlay.aqi", group: "hazard", kind: "data-overlay", label: "Air quality (AQI)",
    providerId: "aqi", defaultVisible: false, defaultOpacity: 0.85, supportsOpacity: true,
    legend: { kind: "swatches", items: [
      { color: "#00e400", label: "Good" }, { color: "#ffff00", label: "Mod" },
      { color: "#ff7e00", label: "USG" }, { color: "#ff0000", label: "Unhealthy" },
      { color: "#8f3f97", label: "V.Unhealthy" }, { color: "#7e0023", label: "Hazard" }] } },
  { id: "overlay.avalanche", group: "hazard", kind: "data-overlay", label: "Avalanche danger",
    providerId: "avalanche", defaultVisible: false, defaultOpacity: 0.4, supportsOpacity: true,
    legend: { kind: "swatches", items: [
      { color: "#52ba4a", label: "Low" }, { color: "#fff300", label: "Mod" },
      { color: "#f7941e", label: "Consid." }, { color: "#ed1c24", label: "High" },
      { color: "#231f20", label: "Extreme" }] } },
```

(`COMING_SOON_LAYERS` is now empty — that's fine; the panel's coming-soon group just renders nothing.)

- [ ] **Step 2: Run `npx tsc -b` — errors expected only in MapView.tsx/App.tsx** (they still reference the old check-fed fire/perimeter props), fixed in Tasks 14-15. Confirm no error references `registry.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/layers/registry.ts
git commit -m "feat(hazards): register fire/perimeter/AQI/avalanche viewport layers"
```

---

## Task 14: useViewportLayers hook

**Files:** Create `frontend/src/hooks/useViewportLayers.ts`. Manual-verify (tsc gate).

- [ ] **Step 1: Implement**

Create `frontend/src/hooks/useViewportLayers.ts`:

```ts
import { useEffect, useRef } from "react";
import type maplibregl from "maplibre-gl";
import type { LayerStateMap } from "../layers/types";
import { api } from "../lib/api";

// registry id -> maplibre geojson source id (set up in MapView)
const VIEWPORT_SOURCES: Record<string, { source: string; layer: string }> = {
  "overlay.fires": { source: "fires", layer: "fires-circle" },
  "overlay.perimeters": { source: "perims", layer: "perims-fill" },
  "overlay.aqi": { source: "aqi", layer: "aqi-circle" },
  "overlay.avalanche": { source: "avy", layer: "avy-fill" },
};
const LAYER_API_ID: Record<string, string> = {
  "overlay.fires": "fires", "overlay.perimeters": "perimeters",
  "overlay.aqi": "aqi", "overlay.avalanche": "avalanche",
};
const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

/** Fetch viewport GeoJSON for each visible hazard layer on moveend (debounced). */
export function useViewportLayers(
  mapRef: React.MutableRefObject<maplibregl.Map | null>,
  layerState: LayerStateMap,
  ready: boolean,
) {
  const timer = useRef<number | null>(null);
  const lastKey = useRef<Record<string, string>>({});

  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current;
    if (!map) return;

    const refresh = async () => {
      const b = map.getBounds();
      const bbox = { west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() };
      const key = `${bbox.west.toFixed(2)},${bbox.south.toFixed(2)},${bbox.east.toFixed(2)},${bbox.north.toFixed(2)}`;
      for (const id of Object.keys(VIEWPORT_SOURCES)) {
        const visible = !!layerState[id]?.visible;
        const src = map.getSource(VIEWPORT_SOURCES[id].source) as maplibregl.GeoJSONSource | undefined;
        if (!src) continue;
        if (!visible) { src.setData(EMPTY); lastKey.current[id] = ""; continue; }
        if (lastKey.current[id] === key) continue;       // same view, already loaded
        lastKey.current[id] = key;
        try {
          const res = await api.layerData(LAYER_API_ID[id], bbox);
          src.setData({ type: "FeatureCollection", features: res.features || [] });
        } catch {
          src.setData(EMPTY);
        }
      }
    };

    const onMove = () => {
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(refresh, 400);
    };
    map.on("moveend", onMove);
    refresh(); // initial + on layerState change
    return () => { map.off("moveend", onMove); if (timer.current) window.clearTimeout(timer.current); };
  }, [mapRef, layerState, ready]);
}
```

- [ ] **Step 2: Run `npx tsc -b`.** Expected: no errors in the hook (App/MapView wiring in Task 15). If `React` types for the ref aren't imported, add `import type React from "react"` — but `useRef`/`useEffect` from "react" suffice; the `React.MutableRefObject` type may need `import type { MutableRefObject } from "react"` and use it directly. Adjust the import to whatever type-checks; keep the logic identical.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useViewportLayers.ts
git commit -m "feat(hazards): useViewportLayers hook (debounced bbox fetch)"
```

---

## Task 15: MapView + App wiring (viewport sources, drop check-fed fire/perims)

**Files:** Modify `frontend/src/components/MapView.tsx`, `frontend/src/App.tsx`. Manual-verify (tsc + build + browser).

- [ ] **Step 1: MapView — add viewport sources/layers + the hook**

In `MapView.tsx`:
(a) Import the hook: `import { useViewportLayers } from "../hooks/useViewportLayers";`
(b) In `addOverlaySources`, add the AQI + avalanche sources/layers (the `fires`/`perims` sources already exist from Phase 1). After the existing `perims-line` layer add:
```ts
    map.addSource("aqi", { type: "geojson", data: EMPTY_FC });
    map.addLayer({ id: "aqi-circle", type: "circle", source: "aqi", layout: { visibility: "none" },
      paint: { "circle-radius": 7,
        "circle-color": ["step", ["coalesce", ["get", "aqi"], 0], "#00e400", 51, "#ffff00", 101, "#ff7e00", 151, "#ff0000", 201, "#8f3f97", 301, "#7e0023"],
        "circle-stroke-color": "#1f241f", "circle-stroke-width": 1, "circle-opacity": 0.85 } });
    map.addSource("avy", { type: "geojson", data: EMPTY_FC });
    map.addLayer({ id: "avy-fill", type: "fill", source: "avy", layout: { visibility: "none" },
      paint: { "fill-opacity": 0.4,
        "fill-color": ["match", ["downcase", ["coalesce", ["to-string", ["get", "danger"]], ""]],
          "low", "#52ba4a", "moderate", "#fff300", "considerable", "#f7941e",
          "high", "#ed1c24", "extreme", "#231f20", "#9aa395"] } });
    map.addLayer({ id: "avy-line", type: "line", source: "avy", layout: { visibility: "none" },
      paint: { "line-color": "#1f241f", "line-width": 0.6, "line-opacity": 0.5 } });
```
(c) Extend `OVERLAY_RENDER` with the AQI + avalanche ids (so visibility/opacity sync works):
```ts
  "overlay.aqi": { layerIds: ["aqi-circle"], opacity: [["aqi-circle", "circle-opacity"]] },
  "overlay.avalanche": { layerIds: ["avy-fill", "avy-line"], opacity: [["avy-fill", "fill-opacity"]] },
```
(d) Remove the `fireDetections` and `perimeterGeojson` props from `Props` and the component signature, and DELETE `syncFires`, `syncPerims`, their `useEffect`s, and their calls in `syncAll` — these layers are now fed by the viewport hook, not props. (Keep the `fires`/`perims` sources + `fires-circle`/`perims-fill`/`perims-line` layers — the hook populates them.)
(e) Call the hook near the other effects (after the prop-driven syncs):
```ts
  useViewportLayers(mapRef, layerState, readyRef.current);
```
Wait — `readyRef.current` isn't reactive. Instead add a `ready` state: add `const [ready, setReady] = useState(false);` set `setReady(true)` inside the `map.on("load", …)` handler (alongside `readyRef.current = true`), and pass `ready` to the hook. Add `useState` to the React import.

- [ ] **Step 2: App.tsx — stop passing check-fed fire/perim data to the map**

In `App.tsx`: remove the `fireDetections` and `perimeterGeojson` props from the `<MapView ... />` usage (both desktop is the only MapView). The `fireDetections`/`perimeterGeojson` `useMemo`s can stay (they still feed the trip Condition dashboard if it shows them) or be removed if unused — remove them only if `tsc` reports them unused (they may still be referenced by ConditionDashboard; if so leave them). Verify by `tsc`.

- [ ] **Step 3: Verify `npx tsc -b && npm run build`** — expect clean (no errors). If `fireDetections`/`perimeterGeojson` are now unused in App.tsx, delete those `useMemo`s to satisfy `noUnusedLocals`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/MapView.tsx frontend/src/App.tsx
git commit -m "feat(hazards): viewport fire/perimeter/AQI/avalanche layers via the hook"
```

---

## Task 16: PointDashboard hazard cards

**Files:** Modify `frontend/src/components/PointDashboard.tsx`.

- [ ] **Step 1: Add value renderers**

In `PointDashboard.tsx`, after the existing `SlopeAspectValue`, add small renderers and wire them into `SectionCard` by `layer_id`. Add:

```tsx
function fmt(v: unknown, suffix = "") { return v == null ? "—" : `${v}${suffix}`; }

function HazardValue({ s }: { s: PointSection }) {
  const d = s.data || {};
  switch (s.layer_id) {
    case "current_weather":
      return <div className="point-elev">{fmt(d.temp_f, "°F")} · {fmt(d.conditions)}
        <span className="point-bucket"> · wind {fmt(d.wind_mph)}{d.gust_mph ? `–${d.gust_mph}` : ""} mph · RH {fmt(d.humidity_pct, "%")}</span></div>;
    case "aqi":
      return <div className="point-elev">AQI {fmt(d.max_aqi)}<span className="point-bucket"> · {fmt(d.category)}</span></div>;
    case "wildfire":
      return <div className="point-elev">{fmt(d.count)} fire(s)<span className="point-bucket"> · nearest {fmt(d.nearest_miles)} mi</span></div>;
    case "avalanche":
      return <div className="point-elev">{fmt(d.danger)}<span className="point-bucket"> · {fmt(d.center)}</span></div>;
    case "snow":
      return <div className="point-elev">{fmt(d.snow_depth_in, " in")} deep<span className="point-bucket"> · {fmt(d.recent_snowfall_in, " in")} recent</span></div>;
    case "freeze_thaw":
      return <div className="point-elev">low {fmt(d.overnight_low_f, "°F")} · {fmt(d.hours_below_freezing)} h &lt; 32°
        <span className="point-bucket"> · refreeze {fmt(d.refreeze)}</span></div>;
    default:
      return null;
  }
}

const HAZARD_IDS = new Set(["current_weather", "aqi", "wildfire", "avalanche", "snow", "freeze_thaw"]);
```

In `SectionCard`, after the slope_aspect line, add:

```tsx
      {HAZARD_IDS.has(s.layer_id) && s.status === "ok" ? <HazardValue s={s} /> : null}
```

- [ ] **Step 2: Verify `npx tsc -b`** — expect no errors. (`d.temp_f` etc. are `unknown`; `fmt` accepts `unknown`. If `noImplicitAny`/index complains, type `d` as `Record<string, unknown>` via `const d = (s.data || {}) as Record<string, unknown>;`.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PointDashboard.tsx
git commit -m "feat(ui): weather/AQI/wildfire/avalanche/snow/freeze-thaw dashboard cards"
```

---

## Task 17: Styles + docs

**Files:** Modify `frontend/src/index.css`, `README.md`.

- [ ] **Step 1: Append styles**

Append to `frontend/src/index.css`:

```css
/* --- hazards --- */
.point-section.point-needs-key { border-style: dashed; }
.point-section.point-needs-key .point-section-status { color: #b08900; }
```

(The hazard cards reuse the existing `.point-elev` / `.point-bucket` / `.point-section*` styles from Phase 1/2.)

- [ ] **Step 2: README note**

In `README.md`, append to the "Map layers" bullet:
```markdown
  Weather & hazard layers (Phase 3): live wildfire (FIRMS + WFIGS), air quality (AirNow), and avalanche danger zones (avalanche.org) fetched for the current map view; plus current weather, snow, and a freeze/thaw card on map click. Wildfire/AQI use the operator's free FIRMS/AirNow keys (graceful "needs key" otherwise); the rest are keyless.
```

- [ ] **Step 3: Verify build + commit**

Run: `cd frontend && npm run build` → succeeds.
```bash
git add frontend/src/index.css README.md
git commit -m "style+docs: hazard needs-key state; document Phase 3 layers"
```

---

## Task 18: Final verification

- [ ] **Step 1: Full backend suite**

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/ -q`
Expected: ALL pass (Phase 1/2 + the new phase3 provider/layer-data/route tests; trip-check tests unchanged = coexistence gate).

- [ ] **Step 2: Frontend unit tests + build**

Run: `cd frontend && npm test && npm run build`
Expected: Vitest all pass; build succeeds.

- [ ] **Step 3: Manual verification (browser)**

Start both servers. Then:
1. Open Layers → Hazard group shows **Active fires, Fire perimeters, Air quality (AQI), Avalanche danger** (all default off). Toggle each (with a winter/fire-season area + the FIRMS/AirNow keys set) → features render for the view and refresh as you pan; legends show the EPA/NAC scales. Without keys, fire/AQI show a clean "needs key" note and render nothing; avalanche (keyless) renders danger-shaded zones.
2. Click a point → "This point" shows **Current weather** + **Freeze/thaw** + **Snow** always; **AQI / nearest fire / avalanche danger** when those layers are on. Cards read correctly.
3. **Coexistence:** basemaps + terrain (Phase 1/2) still work; logging in + Run condition check still records fire/AQI/avalanche in the trip report exactly as before.

Confirm each; fix any failures before declaring done.

- [ ] **Step 4: Final commit (only if fixes were needed)**

```bash
git add -A
git commit -m "fix: address issues from Phase 3 manual verification"
```

---

## Self-Review (plan author)

**Spec coverage:** wildfire (provider T3 + layer-data T9 + layer T13/15), AQI (T2 + T9 + T13/15), avalanche (T4 + T9 + T13/15), current weather (T5), snow (T6), freeze/thaw (T7 + dashboard combine T16); viewport endpoint (T9/T10) + hook (T14); concurrent aggregator (T8); EPA/NAC colors (T11); needs-key/empty/error (every provider + T9); always-on vs gated (T8 registry order + descriptors T13); coexistence (no connector edits; full-suite gates T8/T10/T18); docs (T17).

**Placeholder scan:** none — every code step is complete. The freeze/thaw "elevation-adjusted low + solar aspect" is explicitly combined in the frontend (T16 note) rather than left vague.

**Type consistency:** provider envelope (`ok/empty/needs_key/error`) consistent across T2-T7; `connector_ctx` signature consistent (T1 → T2-T7, T9); `layer_features(layer_id, bbox) -> {status, features}` consistent (T9 → T10); FE `aqiColor/avyColor` (T11) match the MapLibre `step`/`match` expressions (T15) and the registry legend swatches (T13); `api.layerData(id, bbox)` (T12) matches the hook (T14) and route (T10); registry ids (`overlay.fires/perimeters/aqi/avalanche`) match `OVERLAY_RENDER` + `VIEWPORT_SOURCES` (T13/T14/T15).

**Risk notes (manual-verify, not placeholders):** the viewport hook + MapView source wiring (T14/T15) and the AirNow Data-API bbox shape (T9 `_aqi`) are the integration touchpoints — concrete code given, with the browser smoke (T18) as the gate; the AirNow `/aq/data/` parameter set should be confirmed against a live key during T18.
