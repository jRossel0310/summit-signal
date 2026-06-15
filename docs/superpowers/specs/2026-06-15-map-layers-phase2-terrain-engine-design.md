# Map Layers — Phase 2: Terrain Engine (DEM)

**Date:** 2026-06-15
**Status:** Design approved, ready for implementation planning
**Scope:** Phase 2 of the multi-phase "map layers" expansion. Builds directly on Phase 1.
**Depends on:** `2026-06-15-map-layers-phase1-foundation-design.md` (layer registry, `LayerStateMap`, `LayersControl`, point-context provider system, "This point" dashboard).

---

## 1. Context

Phase 1 shipped the layer-system foundation: a frontend layer registry, a hybrid
basemap adapter, a floating `LayersControl` (visibility + opacity + legends), a
backend point-context provider system, and a live "This point" dashboard. It
also left two **"coming soon"** terrain rows (slope, hillshade) and a backend
`slope_aspect` provider **stub**.

Phase 2 makes terrain real: a DEM-backed engine adding **hillshade, slope-angle,
aspect, contours, and a hover elevation readout**, plus a real backend
`SlopeAspectProvider` so clicking a point reports slope° and aspect. Everything
runs **free with no API key** (AWS Terrarium DEM tiles), upgrading to MapTiler
terrain tiles when a key is configured — the same hybrid pattern as Phase 1.

---

## 2. Goals

1. Five terrain layers, all DEM-derived and free-by-default:
   - **Hillshade** via MapLibre's native `raster-dem` + `hillshade`.
   - **Slope angle** with the avalanche-standard 6-bucket ramp, computed client-side.
   - **Aspect** with an 8-way compass-wheel scheme, computed client-side.
   - **Contours** (labeled, free, on-the-fly) via `maplibre-contour`.
   - **Elevation on hover** (click already exists from Phase 1).
2. A real backend `SlopeAspectProvider` feeding "slope/aspect at this point" into
   the dashboard (always-on base context).
3. Reuse Phase 1's registry / state / panel / legend / dashboard with only
   additive, contained extensions.
4. **Zero regression** to Phase 1 layers, basemaps, or the condition-check
   pipeline.

---

## 3. Scope

### In scope (Phase 2)
- DEM source adapter (Terrarium free / MapTiler keyed).
- Hillshade (native), slope + aspect (Web Worker + custom MapLibre protocol),
  contours (`maplibre-contour`), hover elevation readout.
- `SlopeAspectProvider` replacing the Phase 1 stub; `PointDashboard` display for it.
- Vitest for the pure terrain-math + color-mapping functions.

### Out of scope (later phases)
- Weather, snow, freeze/thaw, smoke/AQI, avalanche, current-weather layers (Phase 3).
- Trails / roads / reference vectors (Phase 4).
- Route-profile elevation charts (kept as a future use of the same DEM math).
- 3D terrain / globe.

---

## 4. Coexistence (additive only)

- No change to Phase 1 basemaps or migrated overlays; terrain layers are **new
  registry entries**, all default **off**.
- The condition-check pipeline (`agent/`, `connectors/`, `services/`,
  `routes/checks.py|trips.py`) is **untouched**.
- The only Phase 1 edits are: two registry rows lose `comingSoonPhase` (slope,
  hillshade) and gain real render config; `MapView` gains terrain rendering;
  `PointDashboard` gains a slope/aspect display; `Legend` gains a `"wheel"` kind;
  the backend registry swaps `SlopeAspectStub → SlopeAspectProvider`.
- The "Coming soon" panel group shrinks to just the Phase 3 weather row.

---

## 5. Architecture & data flow

One **DEM source adapter** (`layers/dem.ts`) returns the terrain-RGB tile
template + encoding. Three consumers read it:

1. **Hillshade** — a MapLibre `raster-dem` source (the DEM) + a native
   `hillshade` layer. No custom compute.
2. **Slope & aspect** — a **Web Worker** plus two MapLibre protocols registered
   via `maplibregl.addProtocol`: `slope://{z}/{x}/{y}` and `aspect://{z}/{x}/{y}`.
   On each tile request the worker fetches the DEM tile, decodes elevation,
   computes slope°/aspect per pixel from neighbors, maps to the avalanche ramp /
   aspect wheel, and returns PNG bytes. MapLibre treats these as ordinary raster
   sources — tile-cached, opacity-controlled, legend-backed — so Phase 1's panel
   plumbing works unchanged.
3. **Contours** — `maplibre-contour` (`mlcontour`) wraps the same DEM as a
   `DemSource`, registers its own protocol, and exposes a vector source → contour
   line + label layers.

`MapView` extends its Phase 1 registry-driven rendering to set up these kinds on
map load (register protocols + the contour DemSource once; add raster-dem +
hillshade, the `slope://`/`aspect://` raster sources, and the contour vector
source/layers). Visibility + opacity continue to flow from `LayerStateMap` via
the existing `OVERLAY_RENDER`-style mapping, extended for the new layer ids.

**Backend:** `SlopeAspectProvider` (always-on) samples elevation at the point +
4 neighbors in one batched Open-Meteo call and computes slope/aspect, returned as
a dashboard section. The per-pixel worker math (map shading) and the single-point
Python math (dashboard value) are both small; the Python one is the unit-tested
source of truth for the reported value.

---

## 6. The terrain layers

Group: **Terrain**. Panel + draw order (bottom→top): hillshade · slope · aspect ·
contours. All default **off**.

| Layer (id) | Render | Default opacity | Legend | minzoom |
|---|---|---|---|---|
| Hillshade `overlay.hillshade` | `raster-dem` + native `hillshade` | 0.45 | none | 0 |
| Slope angle `overlay.slope` | `slope://` protocol raster (worker) | 0.55 | 6-bucket avalanche ramp | 10 |
| Aspect `overlay.aspect` *(new)* | `aspect://` protocol raster (worker) | 0.55 | 8-direction wheel | 10 |
| Contours `overlay.contours` *(new)* | `maplibre-contour` vector → line+label | 0.8 (line) | "40 ft / 200 ft index" note | 10 |

**Slope buckets & colors** (avalanche-standard, single source of truth in
`layers/terrainColors.ts`):

| Bucket | Color | Meaning |
|---|---|---|
| 0–15° | `#1a9850` | gentle |
| 15–25° | `#a6d96a` | moderate |
| 25–30° | `#f1e34d` | approaching |
| 30–35° | `#fdae61` | avalanche caution |
| 35–45° | `#d73027` | prime avalanche terrain |
| 45°+ | `#7b3294` | extreme / steep |

**Aspect colors** (8-way; south warm, north cool): N `#3b6fb3`, NE `#3aa6b0`,
E `#5bb86a`, SE `#bcc94a`, S `#e8b53a`, SW `#e07a3a`, W `#b3506f`, NW `#6b5b95`.

**DEM source** (`layers/dem.ts`): default free **AWS Terrarium**
(`https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`,
`encoding: "terrarium"`, `maxzoom: 15`, 256px); when `VITE_MAPTILER_KEY` is set,
MapTiler terrain-RGB (`encoding: "mapbox"`). Attribution surfaced via MapLibre's
attribution control.

**Hover elevation:** when any terrain layer is enabled (DEM tiles already
loaded), `MapView` shows a small elevation chip following the cursor, decoded
client-side from the DEM tile under the pointer — no server call. Click continues
to populate the Phase 1 "This point" dashboard.

---

## 7. Types & interfaces

**`layers/dem.ts`**
```ts
export type DemEncoding = "terrarium" | "mapbox";
export interface DemSourceConfig {
  tiles: string[];
  encoding: DemEncoding;
  tileSize: number;     // 256
  maxzoom: number;      // 15 (Terrarium)
  attribution: string;
}
export function getDemSource(): DemSourceConfig;   // Terrarium free / MapTiler keyed
```

**`layers/terrainColors.ts`** — the single source of truth for both worker
coloring and legends:
```ts
export interface SlopeBucket { min: number; max: number | null; color: string; label: string; }
export const SLOPE_BUCKETS: SlopeBucket[];        // the 6 rows above
export type Direction = "N"|"NE"|"E"|"SE"|"S"|"SW"|"W"|"NW";
export const ASPECT_COLORS: Record<Direction, string>;
export function slopeColor(deg: number): string;  // bucket lookup
export function aspectColor(deg: number): string; // 0..360 -> nearest direction color
```

**Worker messages** (`layers/terrainProtocol.ts` ↔ `layers/terrainWorker.ts`)
```ts
export interface TerrainTileRequest { kind: "slope" | "aspect"; z: number; x: number; y: number; demUrl: string; encoding: DemEncoding; }
// worker returns the encoded PNG bytes (ArrayBuffer) for the tile
```

**`Legend`** (Phase 1 type) gains an optional kind:
```ts
kind: "swatches" | "gradient" | "wheel" | "none";
```
`"wheel"` renders the 8-direction aspect compass; otherwise falls back to 8
labeled swatches.

**Backend** — no new envelope. `SlopeAspectProvider.fetch()` returns
`ProviderResult` with `data = { slope_deg: float, aspect_deg: float,
aspect_compass: str, slope_bucket: str }`. Pure helper:
```python
def compute_slope_aspect(center, north, east, south, west, spacing_m) -> tuple[float, float]:
    """Returns (slope_deg, aspect_deg) from 5 elevations and the ground spacing."""
```

**Slope/aspect math** (shared definition; TS worker per-pixel, Python per-point):
- Terrarium decode: `elev_m = (R*256 + G + B/256) - 32768`.
- MapTiler/mapbox decode: `elev_m = -10000 + (R*65536 + G*256 + B) * 0.1`.
- `dzdx = (east - west) / (2*spacing)`, `dzdy = (north - south) / (2*spacing)`.
- `slope_deg = degrees(atan(hypot(dzdx, dzdy)))`.
- `aspect_deg = (degrees(atan2(-dzdx, -dzdy)) + 360) % 360` — compass bearing of
  the downslope-faced direction, 0 = N, 90 = E, clockwise. (Verify: an
  east-facing slope, where elevation drops toward the east so `dzdx < 0`, gives
  `atan2(+, 0) = 90° = E`, matching the §10 unit test.)
- Worker spacing = meters-per-pixel at the tile; provider spacing = 50 m
  (neighbor offset: `dlat = 50/111320`, `dlon = 50/(111320*cos(lat))`).

---

## 8. Dashboard integration

`backend/app/providers/slope_aspect.py` — `SlopeAspectProvider`:
- `id = "slope_aspect"`, `title = "Slope & aspect"`, `requires_key = None`,
  `always_on = True`.
- Fetches 5 elevations (center + N/E/S/W at 50 m) in **one** Open-Meteo
  elevation request (the API accepts coordinate arrays), computes slope/aspect
  via `compute_slope_aspect`, returns `ok` with the data above. Empty/error on
  failure; **never raises**. Cached by the Phase 1 aggregator cache.
- Registered in `providers/registry.py` `_ALL` in place of `SlopeAspectStub`.
  `SlopeAspectStub` is removed from `providers/stubs.py` (WeatherStub remains).

`PointDashboard` adds a small special-case render for the `slope_aspect` section
(like the elevation big-number): e.g. **"38° · NE · 35–45° band"**, reusing the
existing `SectionCard` status/source handling.

---

## 9. Performance, caching, errors

- One Web Worker computes slope/aspect tiles; MapLibre caches the resulting
  raster tiles (pan-back = no recompute). Worker and `maplibre-contour` share DEM
  tiles via the browser HTTP cache.
- **minzoom 10** on slope/aspect/contours — shading appears when zoomed into
  terrain, avoiding noisy coarse output and continent-scale compute.
- Graceful gaps: DEM fetch failure or ocean/no-data pixels → **transparent
  tile** (map stays usable), not a hard error. Backend provider → `empty`/`error`
  per the Phase 1 contract.
- Attribution (Terrarium/SRTM, maplibre-contour) flows through MapLibre's
  attribution control. No secrets added; MapTiler key remains optional.

---

## 10. Testing

- **Backend (pytest, offline):** `compute_slope_aspect` on known surfaces (flat →
  0°; uniform east-facing → aspect ≈ 90°/E with expected slope); `SlopeAspectProvider`
  with a mocked batched Open-Meteo response → correct `slope_bucket`; failure →
  `error`/`empty`, never raises; asserts all 5 samples go in **one** HTTP request.
  Remove the Phase 1 `test_stub_is_coming_soon` assertion tied to `SlopeAspectStub`.
- **Frontend (Vitest — added this phase):** unit-test the pure functions —
  Terrarium/mapbox decode, `compute slope/aspect` from a small elevation grid,
  `slopeColor`/`aspectColor` bucket/direction mapping. These re-implement the
  backend formula, so the tests also guard against FE/BE divergence. Install:
  `npm install -D vitest`; add `"test": "vitest run"` to `frontend/package.json`.
  DOM/worker glue stays typecheck + manual.

---

## 11. Module / file plan

**New (frontend)**
```
frontend/src/layers/
  dem.ts              # DEM source adapter + DemSourceConfig
  terrainColors.ts    # SLOPE_BUCKETS, ASPECT_COLORS, slopeColor, aspectColor (shared w/ legends)
  terrainProtocol.ts  # registers slope:// and aspect:// protocols; manages the worker
  terrainWorker.ts    # Web Worker: decode DEM tile, compute slope/aspect, color -> PNG
  contours.ts         # maplibre-contour DemSource + layer config (interval)
frontend/src/layers/__tests__/   # Vitest: terrainColors + slope/aspect math
backend/app/providers/
  slope_aspect.py     # SlopeAspectProvider + compute_slope_aspect()
backend/tests/
  test_slope_aspect.py
```

**Modified**
- `frontend/src/layers/registry.ts` — hillshade + slope become real (drop
  `comingSoonPhase`, add render config); add `overlay.aspect`, `overlay.contours`.
- `frontend/src/layers/types.ts` — `Legend.kind` gains `"wheel"`.
- `frontend/src/components/MapView.tsx` — on load: register terrain protocols +
  contour DemSource; add raster-dem + hillshade, slope/aspect raster sources,
  contour vector source/layers; extend visibility/opacity wiring for the new ids;
  add the hover elevation chip.
- `frontend/src/components/PointDashboard.tsx` — slope/aspect section display.
- `frontend/src/components/Legend.tsx` — render the `"wheel"` kind.
- `frontend/package.json` — add `maplibre-contour` (dep) and `vitest` (devDep) +
  `"test": "vitest run"`.
- `backend/app/providers/registry.py` — swap `SlopeAspectStub` → `SlopeAspectProvider`.
- `backend/app/providers/stubs.py` — remove `SlopeAspectStub` (keep `WeatherStub`).
- `backend/tests/test_providers.py` — update for the stub removal.
- `README.md` — note the terrain layers (free DEM; MapTiler upgrade already documented).

---

## 12. Configuration

| Variable | Where | Required | Effect |
|---|---|---|---|
| `VITE_MAPTILER_KEY` | frontend | no | Already from Phase 1. Absent → free Terrarium DEM + free basemaps. Present → MapTiler terrain-RGB DEM (and vector basemaps). |

No backend secrets added. No secrets hardcoded.

---

## 13. Success criteria

- Toggling Hillshade / Slope / Aspect / Contours renders correctly over terrain
  at zoom ≥ 10, with working opacity sliders and matching legends; all run with
  **no API key**.
- Slope shading uses the 6 avalanche buckets; aspect uses the 8-way wheel; both
  match their legends (shared color source).
- Hovering shows a live elevation chip; clicking a point shows **slope° + aspect**
  in the "This point" dashboard alongside elevation.
- Phase 1 layers, basemaps, and the condition-check flow are unchanged
  (full backend suite still green; production build clean).
- `compute_slope_aspect` + color-mapping unit tests pass (pytest + Vitest);
  `tsc -b` clean.
