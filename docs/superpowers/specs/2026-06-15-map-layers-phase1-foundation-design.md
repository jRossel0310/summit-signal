# Map Layers — Phase 1: Layer System Foundation + Basemaps

**Date:** 2026-06-15
**Status:** Design approved, ready for implementation planning
**Scope:** Phase 1 of a larger multi-phase "map layers" expansion for SummitSignal.

---

## 1. Context

SummitSignal is a hiking/mountaineering trip-condition dashboard. The map
(MapLibre GL) today shows OpenTopoMap/OSM basemaps plus a small fixed set of
overlays (selected point, GPX route, fire detections, fire perimeters, saved
trips) toggled by a flat checkbox list in the left `PlanPanel`. Overlay layer
state is a flat `LayerState` interface of booleans; `MapView.tsx` hand-codes
each source/layer.

The user wants to expand the map into a serious, mountaineering-grade,
**terrain-conforming layer system**: temperature/weather, slope angle, aspect,
hillshade, snow, freeze/thaw, avalanche, trails, roads, smoke/AQI, and more —
all toggleable, with legends, opacity, and a live click-to-context dashboard.

That full vision is platform-sized. It is decomposed into a foundation plus
phased layer families (see §3). **This spec covers Phase 1 only:** the
extensible layer-system foundation and the basemap layers.

---

## 2. Goals

1. A typed, extensible **layer system** — a frontend layer registry plus a
   backend data-provider interface — that every future layer plugs into cleanly.
2. A **floating "Layers" map control** (CalTopo/Gaia pattern): grouped layers,
   per-layer visibility + opacity, legends, loading/error/empty states.
3. **Five basemaps** (street, satellite, topo, hybrid, dark) via a hybrid
   adapter that works fully free with no API key and auto-upgrades to MapTiler
   vector styles when a key is configured.
4. A live **"This point" selection dashboard** that updates on map click with
   real elevation now and scaffolded placeholders for future layers.
5. **Zero regression** to the existing condition-check / trip workflow (hard
   constraint — see §5).

---

## 3. The bigger picture (for context only — not built in Phase 1)

The 12 requested layer families collapse onto one foundation and three later
phases. Build order, each its own spec → plan → implementation cycle:

- **Phase 1 (this spec):** Foundation + basemaps + migrate existing overlays.
- **Phase 2 — Terrain engine (DEM):** elevation readout, contours, hillshade,
  slope-angle buckets, aspect. Feeds slope/aspect into the dashboard and into
  freeze/thaw.
- **Phase 3 — Weather & hazards:** current weather (stations), wildfire
  (live provider), smoke/AQI, snow cover, freeze/thaw, avalanche zones
  (pluggable per region).
- **Phase 4 — Reference vectors:** trails, trailheads, route labels, roads/
  access, closures/gates.

The selection dashboard grows each phase. Route-based analysis is kept as an
interface from Phase 1 (`bbox` reserved on `ProviderContext`) and gets a real
implementation once point-based analysis is solid.

---

## 4. Scope

### In scope (Phase 1)

- Frontend layer registry + typed descriptors; `MapView` renders declaratively
  from the registry.
- Backend provider/adapter interface + a `GET /map/point-context` aggregator
  with caching. `ElevationProvider` is real (reuses USGS EPQS logic); other
  providers are stubs returning `coming_soon` with mock data + `TODO` markers.
- Floating `LayersControl`: basemap pick-one group; overlay multi-toggle group
  with visibility + opacity + legend; a dimmed "coming soon" group previewing
  later-phase layers.
- Five basemaps via the hybrid adapter (free default, MapTiler upgrade).
- `PointDashboard` ("This point"): renders the `SelectionResult` sections with
  all status states. Works for anonymous and logged-in users.
- Migration of today's overlays into the registry with **identical** rendering
  and defaults.
- README + `.env.example` documentation for the optional `VITE_MAPTILER_KEY`.

### Out of scope / non-goals (later phases)

- Terrain engine: slope, aspect, hillshade, contours (Phase 2).
- Weather, snow, freeze/thaw, smoke/AQI, avalanche data layers (Phase 3).
- Trails, trailheads, roads/access vector layers (Phase 4).
- Route drawing/import analysis beyond keeping the interface ready (GPX route
  display already exists and is migrated as-is).

---

## 5. Coexistence guarantee (hard constraint)

The existing trip / condition-check feature set must be **untouched**:

- The condition-check pipeline (`agent/jobs.py`, all `connectors/*`,
  `services/risk_engine.py`, `agent/summarizer.py`) and every existing route
  are unchanged.
- Save-trip → run-check → trip detail → print report → re-run-all behave
  exactly as today.
- Fire/perimeter overlays keep rendering from the **same** `check.connector_results`
  data, just routed through the registry instead of being hand-coded.
- The new `GET /map/point-context` is a **separate, read-only path**: no DB
  writes, never invokes the check pipeline.
- The new `LayerStateMap` is a **superset** of today's `LayerState`; every
  currently-default-on layer stays default-on and the topo basemap stays
  default.
- The new "This point" dashboard sits **above** the existing `ConditionDashboard`
  in the right panel; the condition dashboard remains intact below it.

---

## 6. Architecture & data flow

Two registries with one contract — a clean visual/data split:

- **Frontend layer registry** (`frontend/src/layers/`): each layer is a typed
  `LayerDescriptor` (id, group, kind, render config, legend, defaults).
  `MapView` renders from the registry instead of today's hand-coded layers.
  Basemaps and pure-visual overlays live entirely here.
- **Backend provider interface** (`backend/app/providers/`): each data layer
  that needs server-side fetch/compute is a `Provider` with a uniform
  interface, mirroring the existing connector envelope. Phase 1:
  `ElevationProvider` real; the rest are stubs.
- **Aggregator**: `GET /map/point-context?lat=&lon=&layers=` fans out to the
  requested data providers (plus always-on base providers like elevation and
  place name), returns a typed `SelectionResult`, and caches results.

**On map click:**

1. The existing `onSelectPoint(lat, lon)` still fires (sets the trip point —
   unchanged) **and** a new `onPointInspect(lat, lon)` calls
   `api.pointContext(lat, lon, enabledDataLayerIds)`.
2. `PointDashboard` renders the returned `SelectionResult` with loading →
   filled, and per-section status states.
3. The floating panel's toggles drive both map rendering (visibility/opacity)
   and which optional provider sections are requested/shown.

**Map-layer rendering vs dashboard sections are decoupled.** A `LayerDescriptor`
may optionally carry a `providerId` linking it to a dashboard-contributing
provider, but a layer need not render on the map to contribute a section (e.g.
elevation is a dashboard section with no map overlay), and a map overlay need
not have a provider (e.g. migrated fires are fed by the trip check, not the
point-context endpoint, in Phase 1).

---

## 7. Type definitions

### Frontend (`frontend/src/layers/types.ts`)

```ts
// --- Layer metadata (static registry entry) ---
export type LayerKind =
  | "basemap"         // exclusive; swaps the map style
  | "raster-overlay"  // tiled raster over the basemap (Phase 2: slope/hillshade)
  | "vector-overlay"  // geojson lines/fills (perimeters, future trails)
  | "marker"          // geojson points w/ symbols (saved trips, fires, point)
  | "data-overlay";   // backed by a backend provider; also feeds the dashboard

export type LayerGroup =
  | "basemap" | "terrain" | "weather" | "hazard" | "reference" | "trip";

export interface Legend {
  kind: "swatches" | "gradient" | "none";
  items?: { color: string; label: string }[];
  note?: string;
}

export interface LayerDescriptor {
  id: string;               // stable key, e.g. "basemap.topo", "overlay.fires"
  group: LayerGroup;
  kind: LayerKind;
  label: string;
  description?: string;
  legend?: Legend;
  providerId?: string;      // data-overlay → which backend provider feeds it
  requiresKey?: string;     // env var that unlocks/upgrades it
  defaultVisible: boolean;
  defaultOpacity: number;   // 0..1
  supportsOpacity: boolean;
  comingSoonPhase?: number; // if set, shown disabled in the "coming soon" group
  attribution?: string;
}

// --- Layer state (runtime, user-controlled) ---
export interface LayerRuntimeState { visible: boolean; opacity: number; }
export type LayerStateMap = Record<string, LayerRuntimeState>;

// --- Map selection result (what the dashboard renders) ---
export type SectionStatus =
  | "ok" | "loading" | "empty" | "needs-key" | "error" | "coming-soon";

export interface PointSection {
  layerId: string;
  title: string;
  status: SectionStatus;
  data?: Record<string, unknown>;
  message?: string;
  source?: { name: string; url?: string; timestamp?: string };
}

export interface SelectionResult {
  lat: number;
  lon: number;
  placeName?: string;
  sections: PointSection[];
}
```

### Backend (`backend/app/providers/base.py`)

Mirrors the existing connector envelope so it feels native to the codebase.

```python
@dataclass
class ProviderContext:
    latitude: float
    longitude: float
    bbox: dict | None = None        # reserved for future route-based analysis
    settings: dict = field(default_factory=dict)
    shared: dict = field(default_factory=dict)

@dataclass
class ProviderResult:
    provider_id: str
    status: str                     # ok | empty | needs_key | error | coming_soon
    title: str
    data: dict | None = None
    message: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    source_timestamp: str | None = None

class Provider(Protocol):
    id: str
    requires_key: str | None
    always_on: bool                 # base context (elevation, place name) vs toggle-gated
    def fetch(self, ctx: ProviderContext) -> ProviderResult: ...
```

Providers **never raise** — they degrade to an `error` / `needs_key` /
`coming_soon` result, exactly like the existing connectors. A `PROVIDERS`
registry maps `provider_id → instance`. Status values map 1:1 onto the
frontend `SectionStatus` (snake_case → kebab-case at the route boundary).

---

## 8. Basemaps (hybrid adapter)

A single adapter, `frontend/src/layers/basemaps.ts`, exposes
`getBasemapStyle(id): maplibregl.StyleSpecification` so `MapView`'s existing
`setStyle` basemap-swap logic barely changes.

| Basemap   | Free tier (default, no key)             | Keyed upgrade (`VITE_MAPTILER_KEY` set) |
|-----------|------------------------------------------|------------------------------------------|
| Street    | OSM raster *(today)*                      | MapTiler Streets (vector)                |
| Topo      | OpenTopoMap raster *(today)*              | MapTiler Outdoor                         |
| Satellite | Esri World Imagery (no key)               | MapTiler Satellite                       |
| Hybrid    | Esri Imagery + Esri reference labels      | MapTiler Hybrid                          |
| Dark      | CARTO dark-matter raster                  | MapTiler Dataviz Dark                    |

- No key → fully functional on free sources. Key present → auto-upgrades to
  crisper MapTiler vector styles.
- The key is read from `import.meta.env.VITE_MAPTILER_KEY` (Vite convention,
  consistent with `VITE_API_BASE`). Documented in README + `.env.example`. No
  secret is hardcoded; an absent key silently uses the free tier.
- **Phase 2 note:** with a MapTiler key, terrain-RGB tiles for slope/aspect/
  hillshade come from the same key; without one, Phase 2 falls back to free AWS
  Terrarium terrain tiles. Either way Phase 2 is not blocked.
- Attribution for each active source is surfaced via MapLibre's attribution
  control (as today).

---

## 9. Layer panel + "This point" dashboard (UX)

### Floating `LayersControl`

Opens from a button on the map (top-right). Groups:

- **Basemap** — pick-one (radio) list of the five basemaps.
- **Overlays** — multi-toggle list of migrated overlays (saved trips, selected
  point, GPX route, active fires, fire perimeters). Raster/analytical layers
  show an **opacity slider**; each analytical layer shows its **legend**
  swatches. (Phase 1 overlays are mostly markers/vectors; opacity + legend
  infrastructure is built and exercised where applicable.)
- **Coming soon** — dimmed, disabled rows for Phase 2/3 layers (slope angle,
  hillshade, weather/snow), each with a phase badge, so the structure is
  visible from day one.

### `PointDashboard` ("This point")

Renders on map click, above the existing condition dashboard:

- Place name + coordinates (place name from reverse lookup; see §11).
- **Elevation** card — real value with source (`USGS EPQS`) + timestamp
  (`status: ok`).
- Scaffolded sections (slope & aspect, current weather, …) rendered as
  `coming-soon` with a short phase note.
- A `loading` skeleton while the request is in flight.
- Available to anonymous users (the map is public). The logged-out
  trip-conditions area stays as-is (login prompt).

### Mobile

The `LayersControl` is reachable on mobile via a Layers affordance on the
bottom sheet (a segmented option or a floating button that opens a sheet),
preserving the collapsible side-dashboard pattern. The "This point" dashboard
appears in the bottom sheet. Detailed mobile layout finalized during
implementation, following the existing `BottomSheet` patterns.

---

## 10. Migration mapping (zero regression)

| Today (`MapView`)     | Descriptor id        | kind            | Data source (unchanged)          |
|-----------------------|----------------------|-----------------|----------------------------------|
| selected-point marker | `overlay.point`      | marker          | `selectedPoint` prop             |
| GPX route line        | `overlay.gpx`        | vector-overlay  | `selectedTrip.gpx_route.points`  |
| fire detections       | `overlay.fires`      | marker          | check → `nasa_firms`             |
| fire perimeters       | `overlay.perimeters` | vector-overlay  | check → `nifc_wfigs`             |
| saved-trip markers    | `overlay.savedTrips` | marker          | `trips`                          |
| topo/street basemap   | `basemap.*`          | basemap         | basemap adapter                  |

- `LayerState` (flat booleans) → `LayerStateMap`. A seeding helper builds the
  initial state from registry `defaultVisible` / `defaultOpacity`, reproducing
  today's defaults (all overlays on, topo basemap).
- Fire/perimeter overlays still read from `check.connector_results` via the
  existing `useMemo`s in `App.tsx` — no backend change. (Phase 3 may add live
  providers for these; Phase 1 leaves them trip-check-fed.)
- `PlanPanel`'s "Map layers" checkbox block is **removed**; its role moves to
  `LayersControl`.

---

## 11. Caching, errors, loading/empty states

- **Backend cache:** bounded in-memory TTL cache keyed by
  `(provider_id, round(lat, 4), round(lon, 4))`. Elevation is effectively
  static, so a long TTL is safe; the cache is LRU-bounded. Prevents repeated
  clicks from spamming USGS. Reuses the existing `http_client`.
- **Frontend cache:** small in-memory map keyed by rounded lat/lon plus a click
  debounce, so re-clicking the same spot is instant.
- **Per-section status drives the UI:** `ok` (data + source link), `loading`
  (skeleton), `empty` (neutral note), `error` (message + retry, source named),
  `needs-key` (operator-must-set note, **no secret shown**), `coming-soon`
  (phase note). Providers never raise; the aggregator wraps each in try/except
  and returns a per-section status.
- **Place name:** implemented as an `always_on` `PlaceNameProvider` that
  reverse-geocodes the clicked point via Nominatim (the same source already used
  by `/search/location`). Best-effort: on failure it returns an `empty` result
  and the dashboard shows coordinates only (no error surfaced). It runs in the
  aggregator alongside elevation and never blocks the other sections.

---

## 12. Testing

- **Backend (pytest, offline — matches the existing suite):**
  - `ElevationProvider` returns an `ok` result for a mocked point and degrades
    to `error` (never raises) on network failure.
  - Aggregator fans out to requested providers, always includes the base
    providers, caches (a second identical call does not re-hit the source), and
    ignores unknown provider ids gracefully.
  - `GET /map/point-context` returns the `SelectionResult` shape, works without
    auth, and rejects out-of-range coordinates with HTTP 400.
  - Stub providers return `coming_soon` results with mock data.
- **Frontend:** no test runner is added. Correctness is enforced by TypeScript
  (`tsc -b`, already part of `npm run build`) plus manual verification. The
  registry, `layerState` seeding, and `basemaps` adapter are written as pure,
  side-effect-free functions to keep them trivially type-checkable and easy to
  verify by hand.

---

## 13. Module / file plan

**New**

```
frontend/src/layers/
  types.ts            # LayerDescriptor, LayerStateMap, SelectionResult, ...
  registry.ts         # descriptors: basemaps + migrated overlays + coming-soon stubs
  basemaps.ts         # hybrid basemap adapter (free / MapTiler)
  layerState.ts       # seed + update LayerStateMap from registry defaults
frontend/src/components/
  LayersControl.tsx   # floating panel (basemap radios, toggles, opacity, legend)
  PointDashboard.tsx  # "This point" dashboard (sections + all status states)
  Legend.tsx          # small legend renderer
backend/app/providers/
  base.py             # ProviderContext, ProviderResult, Provider, PROVIDERS registry
  elevation.py        # ElevationProvider (reuses USGS EPQS + Open-Meteo fallback logic)
  placename.py        # PlaceNameProvider (always_on; Nominatim reverse geocode, best-effort)
  stubs.py            # coming-soon stub providers (slope, weather, ...) + TODOs
  aggregator.py       # fan-out + TTL/LRU cache
backend/app/routes/
  map.py              # GET /map/point-context
backend/tests/
  test_providers.py
  test_point_context.py
```

**Changed**

- `frontend/src/components/MapView.tsx` — render from the registry; basemap via
  the adapter; overlays declaratively from descriptors + `LayerStateMap`.
- `frontend/src/App.tsx` — `LayerState` → `LayerStateMap`; add the point-inspect
  flow + `PointDashboard`; mount `LayersControl` over the map.
- `frontend/src/components/PlanPanel.tsx` — remove the "Map layers" checkbox
  section.
- Mobile bottom sheet (`App.tsx` / `BottomSheet`) — add the Layers affordance.
- `frontend/src/lib/api.ts` — add `pointContext(lat, lon, layers)`.
- `backend/app/main.py` — include the new map router.
- `README.md` + `.env.example` — document the optional `VITE_MAPTILER_KEY`.

---

## 14. Configuration

| Variable            | Where     | Required | Effect                                                        |
|---------------------|-----------|----------|---------------------------------------------------------------|
| `VITE_MAPTILER_KEY` | frontend  | no       | Absent → free no-key basemaps. Present → MapTiler vector upgrade + terrain-RGB tiles reusable in Phase 2. |

No backend secrets are added in Phase 1. No secrets are hardcoded.

---

## 15. Success criteria

- All five basemaps switch correctly with no key, and upgrade to MapTiler when
  `VITE_MAPTILER_KEY` is set.
- All existing overlays render identically to today, with identical defaults,
  via the new registry.
- The floating `LayersControl` toggles visibility/opacity and shows legends;
  coming-soon layers appear disabled with phase badges.
- Clicking the map populates the "This point" dashboard with real elevation +
  source, scaffolded coming-soon sections, and correct loading/error states —
  for both anonymous and logged-in users.
- The condition-check / trip workflow is verifiably unchanged.
- `tsc -b` passes; backend pytest suite (including new provider/route tests)
  passes offline.
