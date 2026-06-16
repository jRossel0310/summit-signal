# Map Layers — Phase 3: Weather & Hazards

**Date:** 2026-06-15
**Status:** Design approved, ready for implementation planning
**Scope:** Phase 3 of the multi-phase "map layers" expansion. Builds on Phase 1 (layer system + point-context providers) and Phase 2 (terrain engine; aspect/slope reused by freeze/thaw).
**Depends on:** the Phase 1 + Phase 2 design specs in this directory.

---

## 1. Context

Phase 1 shipped the layer registry, `LayersControl`, the point-context provider
system (`GET /map/point-context`), and the "This point" dashboard. Phase 2 added
the terrain engine (hillshade/slope/aspect/contours) and a real
`SlopeAspectProvider`. The original app also has a mature set of condition-check
**connectors** (`nws_weather`, `nasa_firms`, `nifc_wfigs`, `airnow`, `avalanche`,
…) that run inside the saved-trip check pipeline.

Phase 3 turns weather and hazard data into **live map layers + dashboard
sections** — six families: wildfire, smoke/AQI, avalanche zones, current
weather, snow, and freeze/thaw. It **reuses the existing connectors** wherever
possible (wrapping them, not re-implementing) and adds free new sources for the
rest. The condition-check pipeline and its report stay unchanged.

---

## 2. Goals

1. Six weather/hazard families, each as a **point-context provider** (dashboard
   section) and, where it makes sense, a **live viewport map layer**:
   wildfire, smoke/AQI, avalanche danger zones, current weather, snow,
   freeze/thaw.
2. A new **viewport data-layer** mechanism (fetch GeoJSON for the current map
   bounds, live as you pan) — the one genuinely new architectural piece.
3. **Maximum reuse**: providers/layer-data wrap the existing connectors; the
   trip-check pipeline is untouched.
4. **Free-source-first**, graceful `needs-key` for the two keyed sources (FIRMS,
   AirNow), consistent with Phase 1.
5. **Zero regression** to Phase 1/2 layers or the condition-check flow.

---

## 3. Scope

### In scope (Phase 3) — all six families
- **Wildfire**: fire detections (points) + perimeters (polygons) as live
  viewport layers; nearest-fire dashboard section. (Reuse FIRMS + WFIGS.)
- **Smoke / AQI**: AQI monitor markers (viewport, EPA-colored); current-AQI
  dashboard section. "Smoke" folds into air quality (PM2.5 is the smoke proxy).
  (Reuse AirNow.)
- **Avalanche**: danger zones (polygons shaded by NAC danger); your-zone danger
  + center link dashboard section. (Reuse avalanche.org map-layer.)
- **Current weather**: dashboard card only (always-on) — temp, wind/gust,
  humidity, conditions from the nearest NWS station. No map layer. (New: NWS
  station observations.)
- **Snow**: dashboard section — snow depth, recent snowfall, SWE if available,
  snowline estimate. Raster snow-cover overlay is **best-effort/stretch**.
  (New: Open-Meteo snow fields.)
- **Freeze / thaw**: dashboard card (the marquee) — overnight low by elevation,
  hours below freezing, refreeze likelihood, morning warming, solar-aspect note.
  (Derived: NWS + lapse-rate + Phase 2 aspect/slope.) No map layer.

### Out of scope (later)
- Trails / trailheads / roads (Phase 4).
- Dedicated HRRR-Smoke forecast layer (noted as future; AQI covers smoke now).
- Route-based hazard analysis (the point/viewport model is built so it can be
  added later).
- Avalanche problem roses / observations feeds (zones + danger only this phase).

---

## 4. Coexistence (additive only)

- The condition-check pipeline (`agent/`, all `connectors/*`,
  `services/risk_engine.py`, `summarizer.py`, `routes/checks.py`,
  `routes/trips.py`) and the trip report are **untouched**. Phase 3 providers and
  layer-data **wrap** the connectors (build a minimal `ConnectorContext`, call
  `connector.run()`, translate the output) — no connector edits.
- `overlay.fires` / `overlay.perimeters` switch their **map** data source from
  "selected trip's check result" to the live viewport endpoint. The trip check
  still records fire/AQI/avalanche for the saved-trip report exactly as before.
- Phase 1/2 layers, basemaps, terrain, and the existing point providers are
  unchanged. The `WeatherStub` placeholder is retired.

---

## 5. Architecture & data flow

Two additions on the established pattern:

**A. Point-context providers** (extend Phase 1's aggregator, like `slope_aspect`):
`current_weather`, `aqi`, `wildfire`, `snow`, `freeze_thaw`, `avalanche`. Each
wraps a connector or a new free source and returns a `ProviderResult` dashboard
section. The three **dashboard-only** families — `current_weather`, `snow`,
`freeze_thaw` — are **always-on cards**; the three with viewport map layers —
`aqi`, `wildfire`, `avalanche` — are **layer-gated** (run when their layer is
enabled, via the existing `enabledDataProviderIds`). To keep clicks snappy with
several always-on providers, the aggregator's fan-out becomes **concurrent**
(an I/O-bound thread pool runs the providers in parallel and collects results in
stable order) — a contained Phase 1 enhancement; providers are independent and
never raise. NWS-based providers (`current_weather`, `freeze_thaw`) share the
fetched forecast via `ProviderContext.shared` to avoid a duplicate NWS call.

**B. Viewport data-layer endpoint** `GET /map/layer/{id}?west=&south=&east=&north=`
→ `{ status, features }` (GeoJSON `FeatureCollection`). A `LayerDataProvider`
per id (fire, perimeters, avalanche, aqi) fetches the connector data for the
bbox and returns GeoJSON. Keys stay server-side; cached by `(id, rounded bbox)`
with per-layer TTL. Never raises → empty FC + `status` (`ok|needs_key|error`).

**Frontend** `useViewportLayers` hook: for each visible viewport layer, fetch its
bbox GeoJSON on debounced `moveend` (+ on toggle-on), `setData` the layer's
GeoJSON source, abort stale requests, cache by rounded bbox. `needs-key`/`error`/
`empty` surfaced as a small status note in that layer's `LayersControl` row.

**On map click** (unchanged Phase 1 flow): `pointContext` now also returns the
new always-on + enabled hazard sections; `PointDashboard` renders them.

---

## 6. The six families

Canonical color schemes: **EPA AQI** categories (Good green `#00e400`, Moderate
yellow `#ffff00`, USG orange `#ff7e00`, Unhealthy red `#ff0000`, Very Unhealthy
purple `#8f3f97`, Hazardous maroon `#7e0023`); **NAC avalanche danger** (Low
green `#52ba4a`, Moderate yellow `#fff300`, Considerable orange `#f7941e`, High
red `#ed1c24`, Extreme black `#231f20`).

| Family | Map layer (viewport) | Dashboard section | Source | Key |
|---|---|---|---|---|
| Wildfire | fire points + perimeter polygons | nearest fire: distance, confidence, count | FIRMS + WFIGS *(reuse)* | FIRMS |
| Smoke/AQI | AQI monitor markers (EPA-colored) | current AQI + category + dominant pollutant | AirNow *(reuse)* | AirNow |
| Avalanche | danger zones (NAC-shaded polygons) | your zone: danger level, center, forecast link | avalanche.org map-layer *(reuse)* | none |
| Current weather | — (dashboard only) | temp, wind/gust, humidity, conditions, station + time | NWS station obs *(new)* | none |
| Snow | *(dashboard-first; raster stretch)* | snow depth, recent snowfall, SWE, snowline est. | Open-Meteo *(new)* | none |
| Freeze/thaw | *(dashboard only)* | see §7 | derived *(new)* | none |

Data-source notes:
- **Wildfire**: FIRMS area CSV (existing connector) → detection points; WFIGS
  ArcGIS perimeters (existing connector) → polygons. Both bbox-driven.
- **AQI**: point dashboard reuses the AirNow observation connector; the viewport
  marker layer uses AirNow's bbox **Data API** (`/aq/data/`), translated to
  point features colored by AQI category.
- **Avalanche**: the avalanche.org map-layer GeoJSON (already fetched by the
  connector) carries a per-zone `danger` property → shade polygons; the point
  section reuses the connector's point-in-zone result.
- **Current weather**: NWS `/points/{lat,lon}` → `observationStations` →
  nearest station `/observations/latest` (temp, wind, gust, humidity, text).
- **Snow**: Open-Meteo forecast API `current/hourly` `snow_depth` + `snowfall`;
  snowline estimate from the forecast freezing level (or lapse-rate fallback).

---

## 7. Freeze/thaw card (marquee, derived)

A `freeze_thaw` always-on provider combining the NWS hourly forecast, the point
elevation (lapse-rate ~3.5 °F/1000 ft, reusing the `elevation_adjusted` logic),
and Phase 2 aspect/slope. Card fields:
- **Overnight low** at the point's elevation (lapse-adjusted from the valley
  forecast low).
- **Hours below freezing** in the next 24 h (count of hourly temps < 32 °F,
  elevation-adjusted).
- **Refreeze likelihood** — heuristic: daytime high > 32 °F **and** overnight low
  < ~28 °F → "good refreeze likely"; 28–32 °F overnight → "marginal"; never below
  32 → "no refreeze".
- **Morning warming trend** — °F/hour climb after sunrise (the "be off by…" cue).
- **Solar-aspect note** — S/SW + sun → faster softening / wet-slide concern;
  N-facing → stays firm longer (from Phase 2 aspect).

`ok | empty (no forecast) | error`, never raises, cached by the aggregator.

---

## 8. Types & interfaces

**Backend**
- Six providers implement the Phase 1 `Provider` protocol (`id`, `title`,
  `requires_key`, `always_on`, `fetch(ctx) -> ProviderResult`). `requires_key`
  set for `wildfire` (FIRMS) and `aqi` (AirNow); `None` for the rest.
- `services/layer_data.py`:
  ```python
  class LayerDataProvider(Protocol):
      id: str
      requires_key: str | None
      def fetch_bbox(self, bbox: dict, ctx: ProviderContext) -> dict: ...  # GeoJSON FeatureCollection
  LAYER_DATA: dict[str, LayerDataProvider]   # "fires","perimeters","avalanche","aqi"
  def layer_features(layer_id, bbox, settings) -> dict  # {status, features}, cached, never raises
  ```
- Pydantic `LayerDataResponse { status: str; features: list[dict] }` (GeoJSON
  passthrough) for `GET /map/layer/{id}`.
- **Connector reuse**: each provider/layer-data builds a `ConnectorContext`
  (lat/lon or bbox + api_keys from the same source the check pipeline uses) and
  calls the connector's `run()`, then maps `normalized` → result. No connector
  edits.

**Frontend**
- `layers/hazardColors.ts`: `AQI_CATEGORIES` (breakpoint → color/label) +
  `aqiColor(aqi)`; `AVY_DANGER` (level → color/label) + `avyColor(level)`.
- Registry descriptors: `overlay.fires`/`overlay.perimeters` become viewport
  `data-overlay` layers (providerId set); add `overlay.aqi` and
  `overlay.avalanche` (viewport data-overlays, each with a `providerId` so its
  dashboard section is gated correctly). The Phase 1 `overlay.weather`
  placeholder is **removed** — `current_weather`/`snow`/`freeze_thaw` are
  always-on section-only providers with no map layer.
- `hooks/useViewportLayers.ts`: `(map, layerState) -> void` side-effect hook
  managing the bbox fetch + setData + abort + cache.
- `lib/api.ts`: `layerData(id, bbox)` returning `{status, features}`.

---

## 9. Caching, errors, needs-key, states

- **Backend**: point-providers cached by the Phase 1 aggregator cache. Area
  endpoint cached by `(id, rounded bbox)` with TTL (fire ~5 min, AQI ~15 min,
  avalanche ~30 min, perimeters ~30 min). Bounded LRU. Everything degrades:
  missing key → `needs_key` + empty features; fetch failure → `error` + empty.
- **Frontend**: viewport fetches debounced (~400 ms after `moveend`), in-flight
  aborted on the next move, results cached by rounded bbox; the point cache from
  Phase 1 is reused. Per-layer status note in the panel for `needs-key`/`error`/
  `empty`. AQI/danger legends in the panel (reusing the Legend component;
  swatches for the category scales).
- **Empty world**: with no FIRMS/AirNow key set, those layers render nothing and
  show a one-line "needs operator key" note; everything else works.

---

## 10. Testing

- **Backend (pytest, offline)**: each provider with a monkeypatched connector /
  HTTP client → `ok` with the right mapped fields; `needs_key` when the key is
  absent; `error`/`empty` on failure; never raises. `layer_features` dispatch +
  cache (second identical bbox doesn't re-fetch) + unknown id. `GET /map/layer/{id}`
  route shape, bbox validation (400 on bad bbox), no-auth. The freeze/thaw
  heuristic on known forecast inputs. **Full suite re-run** = the trip-check
  coexistence gate.
- **Frontend (Vitest)**: `aqiColor`/`avyColor` category mapping; any pure
  freeze/thaw or snowline helper. The `useViewportLayers` hook + map rendering
  and the dashboard cards via `tsc -b` + manual.

---

## 11. Module / file plan

**Backend new**
```
app/providers/current_weather.py   # NWS nearest-station obs
app/providers/aqi.py               # wraps airnow connector
app/providers/wildfire.py          # nearest-fire summary (wraps nasa_firms)
app/providers/snow.py              # Open-Meteo snow depth/snowfall/snowline
app/providers/freeze_thaw.py       # derived (NWS + lapse + aspect)
app/providers/avalanche.py         # point zone danger (wraps avalanche connector)
app/services/layer_data.py         # bbox -> GeoJSON dispatch (fires/perimeters/avalanche/aqi)
app/tests/test_phase3_providers.py, test_layer_data.py
```
**Backend modified**: `routes/map.py` (+`/map/layer/{id}`), `schemas.py`
(`LayerDataResponse`), `providers/registry.py` (+6 providers, retire
`WeatherStub`), `providers/stubs.py` (drop `WeatherStub`),
`tests/test_providers.py` (stub-test update).

**Frontend new**
```
src/layers/hazardColors.ts         # AQI + NAC danger palettes + tests
src/hooks/useViewportLayers.ts     # viewport bbox fetch + setData + abort + cache
```
**Frontend modified**: `layers/registry.ts` (hazard layers), `components/MapView.tsx`
(viewport GeoJSON sources + hook wiring; fire/perimeter/avalanche/aqi sources),
`components/PointDashboard.tsx` (weather/aqi/avalanche/freeze-thaw/snow cards),
`lib/api.ts` (+`layerData`), `index.css`, `README.md`.

---

## 12. Configuration

| Variable | Where | Required | Effect |
|---|---|---|---|
| `SUMMIT_SIGNAL_FIRMS_KEY` | backend | no | Absent → wildfire layer/section `needs-key`. Present → live fire detections. (Already used by the check pipeline.) |
| `SUMMIT_SIGNAL_AIRNOW_KEY` | backend | no | Absent → AQI layer/section `needs-key`. Present → live AQI. (Already used by the check pipeline.) |

No new secrets; reuses the operator keys the check pipeline already reads. NWS,
Open-Meteo, and avalanche.org are keyless.

---

## 13. Success criteria

- Toggling Wildfire / AQI / Avalanche fetches and renders features for the
  current viewport, refreshing as you pan (debounced), with correct EPA/NAC
  colors and legends; `needs-key` shown cleanly when a key is absent.
- Clicking a point shows current weather + freeze/thaw always, and AQI / nearest
  fire / avalanche danger / snow when those layers are on — each a clear card.
- The freeze/thaw card shows overnight low (elevation-adjusted), hours below
  freezing, refreeze likelihood, morning warming, and the aspect note.
- Phase 1/2 layers and the condition-check flow are unchanged (full backend
  suite green; production build clean).
- Provider/color/heuristic unit tests pass (pytest + Vitest); `tsc -b` clean.
