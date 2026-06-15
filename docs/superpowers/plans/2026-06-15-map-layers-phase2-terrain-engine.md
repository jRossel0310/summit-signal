# Map Layers — Phase 2 Terrain Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a DEM-backed terrain engine — native hillshade, client-computed slope-angle + aspect shading (Web Worker + custom MapLibre protocol), free on-the-fly contours (maplibre-contour), a hover elevation readout, and a real backend slope/aspect provider feeding the "This point" dashboard — all free with no API key, building on the Phase 1 layer system.

**Architecture:** One DEM source adapter feeds three consumers: MapLibre's native `raster-dem`+`hillshade`; a Web Worker that computes colored slope/aspect raster tiles served via `addProtocol`; and `maplibre-contour` for contour vector tiles. Slope/aspect at a clicked point comes from a new always-on backend `SlopeAspectProvider`. Everything slots into Phase 1's registry / `LayerStateMap` / `LayersControl` / `PointDashboard`.

**Tech Stack:** Backend — FastAPI, httpx, pytest. Frontend — Vite + React + TypeScript + MapLibre GL, `maplibre-contour`, Web Workers/OffscreenCanvas; **Vitest** (new) for pure terrain math.

**Spec:** `docs/superpowers/specs/2026-06-15-map-layers-phase2-terrain-engine-design.md`

---

## Conventions

- **Worktree:** all work in `C:/Users/jacob/summit-signal/.claude/worktrees/map-layers-phase1-impl`, branch `worktree-map-layers-phase1-impl`. Commit after each task; do not push.
- **Backend tests:** `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/<file> -q` (the default `python` lacks pytest).
- **Frontend type check:** `cd frontend && npx tsc -b` (must be exit 0).
- **Frontend unit tests (new):** `cd frontend && npm test` (runs `vitest run`).
- **Wire format is snake_case** (matches `src/types.ts`).
- Phase 1 is complete on this branch; Phase 2 is **additive** — do not alter Phase 1 layers, basemaps, or the condition-check pipeline.

---

## File Structure

**Backend (new):** `app/providers/slope_aspect.py` (compute helpers + `SlopeAspectProvider`), `tests/test_slope_aspect.py`.
**Backend (modified):** `app/providers/registry.py` (swap stub→provider), `app/providers/stubs.py` (drop `SlopeAspectStub`), `tests/test_providers.py` (update stub test).

**Frontend (new):** `src/layers/dem.ts`, `src/layers/terrainColors.ts`, `src/layers/terrainMath.ts`, `src/layers/terrainProtocol.ts`, `src/layers/terrainWorker.ts`, `src/layers/contours.ts`, plus co-located `*.test.ts` for the pure modules.
**Frontend (modified):** `src/layers/types.ts` (Legend `"wheel"`), `src/layers/registry.ts` (terrain layers real), `src/components/Legend.tsx` (wheel render), `src/components/MapView.tsx` (terrain rendering + hover chip), `src/components/PointDashboard.tsx` (slope/aspect display), `src/index.css` (styles), `package.json` (+deps), `README.md`.

---

## Task 1: Backend slope/aspect math helpers

**Files:**
- Create: `backend/app/providers/slope_aspect.py` (helpers only this task)
- Test: `backend/tests/test_slope_aspect.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_slope_aspect.py`:

```python
"""Pure slope/aspect math + provider tests. Offline."""
import math
from app.providers.slope_aspect import (
    compute_slope_aspect, slope_bucket_label, aspect_compass,
)


def test_flat_surface_is_zero_slope():
    slope, _aspect = compute_slope_aspect(100, 100, 100, 100, 100, spacing_m=50)
    assert slope == 0.0


def test_east_facing_slope_has_east_aspect():
    # elevation drops toward the east: east lower, west higher -> faces east (~90)
    slope, aspect = compute_slope_aspect(center=100, north=100, east=50, south=100, west=150, spacing_m=50)
    assert slope > 0
    assert abs(aspect - 90.0) < 0.5


def test_north_facing_slope_has_north_aspect():
    # drops toward the north -> faces north (~0/360)
    _slope, aspect = compute_slope_aspect(center=100, north=50, east=100, south=150, west=100, spacing_m=50)
    assert aspect < 0.5 or aspect > 359.5


def test_slope_bucket_labels():
    assert slope_bucket_label(5) == "0–15°"
    assert slope_bucket_label(32) == "30–35°"
    assert slope_bucket_label(40) == "35–45°"
    assert slope_bucket_label(60) == "45°+"


def test_aspect_compass_directions():
    assert aspect_compass(0) == "N"
    assert aspect_compass(90) == "E"
    assert aspect_compass(180) == "S"
    assert aspect_compass(270) == "W"
    assert aspect_compass(45) == "NE"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/test_slope_aspect.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.providers.slope_aspect'`

- [ ] **Step 3: Write the helpers**

Create `backend/app/providers/slope_aspect.py`:

```python
"""SlopeAspectProvider + pure slope/aspect math.

Map-shading slope/aspect is computed client-side in a worker; this module is the
unit-tested source of truth for the single-point value shown in the dashboard."""
from __future__ import annotations
import math

# Slope buckets (avalanche-standard). Boundaries shared in spirit with the
# frontend terrainColors.ts; the two live in different languages.
_BUCKETS = [(0, 15, "0–15°"), (15, 25, "15–25°"), (25, 30, "25–30°"),
            (30, 35, "30–35°"), (35, 45, "35–45°"), (45, None, "45°+")]
_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compute_slope_aspect(center, north, east, south, west, spacing_m) -> tuple[float, float]:
    """Returns (slope_deg, aspect_deg) from 5 elevations (m) and the ground
    spacing (m). aspect_deg is the compass bearing of the downslope-faced
    direction: 0 = N, 90 = E, clockwise."""
    dzdx = (east - west) / (2.0 * spacing_m)
    dzdy = (north - south) / (2.0 * spacing_m)
    slope = math.degrees(math.atan(math.hypot(dzdx, dzdy)))
    if dzdx == 0 and dzdy == 0:
        return 0.0, 0.0
    aspect = (math.degrees(math.atan2(-dzdx, -dzdy)) + 360.0) % 360.0
    return slope, aspect


def slope_bucket_label(deg: float) -> str:
    for lo, hi, label in _BUCKETS:
        if deg >= lo and (hi is None or deg < hi):
            return label
    return _BUCKETS[-1][2]


def aspect_compass(deg: float) -> str:
    return _COMPASS[int((deg % 360) / 45.0 + 0.5) % 8]
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/test_slope_aspect.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/slope_aspect.py backend/tests/test_slope_aspect.py
git commit -m "feat(providers): slope/aspect math helpers (compute, bucket, compass)"
```

---

## Task 2: SlopeAspectProvider (batched Open-Meteo)

**Files:**
- Modify: `backend/app/providers/slope_aspect.py` (add the provider class)
- Test: `backend/tests/test_slope_aspect.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_slope_aspect.py`:

```python
from app.providers import slope_aspect as sa_mod
from app.providers.base import ProviderContext


class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        return None
    def json(self):
        return self._p


class _OneCallClient:
    """Records calls; returns 5 elevations (center,N,E,S,W) for any request."""
    def __init__(self, elevations):
        self.elevations = elevations
        self.calls = 0
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def get(self, url, params=None):
        self.calls += 1
        return _Resp({"elevation": self.elevations})


def test_provider_ok_single_request(monkeypatch):
    # center,N,E,S,W : east lower than west -> east-facing
    client = _OneCallClient([1000, 1000, 950, 1000, 1050])
    monkeypatch.setattr(sa_mod, "http_client", lambda: client)
    out = sa_mod.SlopeAspectProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["aspect_compass"] == "E"
    assert out.data["slope_deg"] > 0
    assert "°" in out.data["slope_bucket"]
    assert client.calls == 1   # all 5 samples in ONE request


def test_provider_never_raises(monkeypatch):
    class _Boom:
        def __enter__(self): raise RuntimeError("down")
        def __exit__(self, *a): return False
    monkeypatch.setattr(sa_mod, "http_client", lambda: _Boom())
    out = sa_mod.SlopeAspectProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status in ("error", "empty")


def test_provider_empty_when_no_elevations(monkeypatch):
    monkeypatch.setattr(sa_mod, "http_client", lambda: _OneCallClient([]))
    out = sa_mod.SlopeAspectProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status in ("empty", "error")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/test_slope_aspect.py -q`
Expected: FAIL with `AttributeError: module 'app.providers.slope_aspect' has no attribute 'SlopeAspectProvider'`

- [ ] **Step 3: Add the provider**

Add to the TOP imports of `backend/app/providers/slope_aspect.py` (below `import math`):

```python
from ..connectors.base import http_client, utcnow_iso
from .base import ProviderContext, ProviderResult, ok, empty, error

OPEN_METEO_URL = "https://api.open-meteo.com/v1/elevation"
_SPACING_M = 50.0
```

Append to `backend/app/providers/slope_aspect.py`:

```python
class SlopeAspectProvider:
    id = "slope_aspect"
    title = "Slope & aspect"
    requires_key = None
    always_on = True

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        lat, lon = ctx.latitude, ctx.longitude
        dlat = _SPACING_M / 111320.0
        dlon = _SPACING_M / (111320.0 * max(0.1, math.cos(math.radians(lat))))
        # order: center, north, east, south, west
        lats = [lat, lat + dlat, lat, lat - dlat, lat]
        lons = [lon, lon, lon + dlon, lon, lon - dlon]
        try:
            with http_client() as client:
                r = client.get(OPEN_METEO_URL, params={
                    "latitude": ",".join(f"{v:.6f}" for v in lats),
                    "longitude": ",".join(f"{v:.6f}" for v in lons)})
                r.raise_for_status()
                elevs = r.json().get("elevation") or []
                if len(elevs) < 5 or any(e is None for e in elevs[:5]):
                    return empty(self.id, self.title, "No elevation data at this point")
                c, n, e, s, w = (float(x) for x in elevs[:5])
                slope, aspect = compute_slope_aspect(c, n, e, s, w, _SPACING_M)
                return ok(self.id, self.title, data={
                    "slope_deg": round(slope, 1),
                    "aspect_deg": round(aspect, 1),
                    "aspect_compass": aspect_compass(aspect),
                    "slope_bucket": slope_bucket_label(slope),
                }, source_name="Open-Meteo elevation (5-sample slope estimate)",
                   source_url=OPEN_METEO_URL, source_timestamp=utcnow_iso())
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/test_slope_aspect.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/slope_aspect.py backend/tests/test_slope_aspect.py
git commit -m "feat(providers): SlopeAspectProvider (batched Open-Meteo, always-on)"
```

---

## Task 3: Wire provider into registry, drop stub, full suite

**Files:**
- Modify: `backend/app/providers/registry.py`
- Modify: `backend/app/providers/stubs.py`
- Modify: `backend/tests/test_providers.py`

- [ ] **Step 1: Swap the registry**

In `backend/app/providers/registry.py`, change the imports + `_ALL`. Replace:

```python
from . import stubs

_ALL: list[Provider] = [
    PlaceNameProvider(),
    ElevationProvider(),
    stubs.SlopeAspectStub,
    stubs.WeatherStub,
]
```

with:

```python
from . import stubs
from .slope_aspect import SlopeAspectProvider

_ALL: list[Provider] = [
    PlaceNameProvider(),
    ElevationProvider(),
    SlopeAspectProvider(),
    stubs.WeatherStub,
]
```

- [ ] **Step 2: Remove the slope stub**

In `backend/app/providers/stubs.py`, delete the `SlopeAspectStub = ...` line and the `TODO(phase-2)` comment line, leaving `WeatherStub` and the `TODO(phase-3)` note. The file's `SlopeAspectStub` definition (last-but-one line) is removed; `WeatherStub = _ComingSoon("weather", "Current weather", 3)` stays.

- [ ] **Step 3: Update the stub test**

In `backend/tests/test_providers.py`, the `test_stub_is_coming_soon` test references `stubs.SlopeAspectStub`. Replace its body to use the remaining `WeatherStub`:

```python
def test_stub_is_coming_soon():
    out = stubs.WeatherStub.fetch(ProviderContext(40.0, -105.0))
    assert out.status == "coming_soon"
    assert out.provider_id == "weather"
```

- [ ] **Step 4: Run the FULL backend suite (regression gate)**

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/ -q`
Expected: ALL pass. Note: the Phase 1 `test_point_context_includes_coming_soon` uses `layers=weather`, which still maps to `WeatherStub` → `coming-soon`, so it stays green. `select_providers(None)` now includes `slope_aspect` as always-on.

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/registry.py backend/app/providers/stubs.py backend/tests/test_providers.py
git commit -m "feat(providers): register SlopeAspectProvider, retire slope stub"
```

---

## Task 4: Frontend deps — maplibre-contour + Vitest

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install the dependencies**

Run:
```bash
cd frontend && npm install maplibre-contour && npm install -D vitest
```
Expected: both install successfully; `package.json` gains `"maplibre-contour"` under dependencies and `"vitest"` under devDependencies.

- [ ] **Step 2: Add the test script**

In `frontend/package.json`, add a `"test"` script to the `"scripts"` block (alongside `dev`/`build`/`preview`):

```json
    "test": "vitest run"
```

- [ ] **Step 3: Verify install + type check**

Run: `cd frontend && npx tsc -b`
Expected: no errors (the new deps don't break the build; no source uses them yet).

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "build(frontend): add maplibre-contour dep and vitest test runner"
```

---

## Task 5: terrainColors — shared color source (Vitest)

**Files:**
- Create: `frontend/src/layers/terrainColors.ts`
- Test: `frontend/src/layers/terrainColors.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/layers/terrainColors.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { SLOPE_BUCKETS, ASPECT_COLORS, slopeColor, aspectColor } from "./terrainColors";

describe("slope buckets", () => {
  it("has the six avalanche buckets", () => {
    expect(SLOPE_BUCKETS.map((b) => b.label)).toEqual(
      ["0–15°", "15–25°", "25–30°", "30–35°", "35–45°", "45°+"],
    );
  });
  it("maps a degree to the right bucket color", () => {
    expect(slopeColor(5)).toBe("#1a9850");
    expect(slopeColor(40)).toBe("#d73027");
    expect(slopeColor(60)).toBe("#7b3294");
  });
});

describe("aspect colors", () => {
  it("has 8 directions", () => {
    expect(Object.keys(ASPECT_COLORS)).toHaveLength(8);
  });
  it("maps degrees to the nearest direction color", () => {
    expect(aspectColor(0)).toBe(ASPECT_COLORS.N);
    expect(aspectColor(90)).toBe(ASPECT_COLORS.E);
    expect(aspectColor(225)).toBe(ASPECT_COLORS.SW);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL (cannot find module `./terrainColors`).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/layers/terrainColors.ts`:

```ts
// Single source of truth for slope/aspect coloring — used by BOTH the worker
// (pixel shading) and the legends (so they can never drift apart).

export interface SlopeBucket { min: number; max: number | null; color: string; label: string; }

export const SLOPE_BUCKETS: SlopeBucket[] = [
  { min: 0, max: 15, color: "#1a9850", label: "0–15°" },
  { min: 15, max: 25, color: "#a6d96a", label: "15–25°" },
  { min: 25, max: 30, color: "#f1e34d", label: "25–30°" },
  { min: 30, max: 35, color: "#fdae61", label: "30–35°" },
  { min: 35, max: 45, color: "#d73027", label: "35–45°" },
  { min: 45, max: null, color: "#7b3294", label: "45°+" },
];

export type Direction = "N" | "NE" | "E" | "SE" | "S" | "SW" | "W" | "NW";

export const ASPECT_COLORS: Record<Direction, string> = {
  N: "#3b6fb3", NE: "#3aa6b0", E: "#5bb86a", SE: "#bcc94a",
  S: "#e8b53a", SW: "#e07a3a", W: "#b3506f", NW: "#6b5b95",
};

const DIRECTIONS: Direction[] = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

export function slopeColor(deg: number): string {
  for (const b of SLOPE_BUCKETS) {
    if (deg >= b.min && (b.max === null || deg < b.max)) return b.color;
  }
  return SLOPE_BUCKETS[SLOPE_BUCKETS.length - 1].color;
}

export function aspectColor(deg: number): string {
  const idx = Math.round(((deg % 360) + 360) % 360 / 45) % 8;
  return ASPECT_COLORS[DIRECTIONS[idx]];
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS (2 files? no — 1 file, all tests pass).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/layers/terrainColors.ts frontend/src/layers/terrainColors.test.ts
git commit -m "feat(terrain): shared slope/aspect color source + tests"
```

---

## Task 6: terrainMath — DEM decode + slope/aspect (Vitest)

**Files:**
- Create: `frontend/src/layers/terrainMath.ts`
- Test: `frontend/src/layers/terrainMath.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/layers/terrainMath.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { decodeTerrarium, decodeMapbox, pixelSlopeAspect, metersPerPixel } from "./terrainMath";

describe("DEM decode", () => {
  it("decodes terrarium sea level (32768,0,0 -> 0m)", () => {
    expect(decodeTerrarium(128, 0, 0)).toBeCloseTo(0, 5); // 128*256 = 32768 -> -32768 +32768 = 0
  });
  it("decodes mapbox base (-10000m at 0,0,0)", () => {
    expect(decodeMapbox(0, 0, 0)).toBeCloseTo(-10000, 5);
  });
});

describe("pixelSlopeAspect", () => {
  it("flat -> 0 slope", () => {
    const { slope } = pixelSlopeAspect(100, 100, 100, 100, 100, 30);
    expect(slope).toBe(0);
  });
  it("east-facing -> ~90 aspect", () => {
    // east lower, west higher
    const { slope, aspect } = pixelSlopeAspect(100, 100, 50, 100, 150, 30);
    expect(slope).toBeGreaterThan(0);
    expect(Math.abs(aspect - 90)).toBeLessThan(0.5);
  });
});

describe("metersPerPixel", () => {
  it("is positive and shrinks with zoom", () => {
    const z5 = metersPerPixel(40, 5);
    const z12 = metersPerPixel(40, 12);
    expect(z5).toBeGreaterThan(z12);
    expect(z12).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL (cannot find `./terrainMath`).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/layers/terrainMath.ts`:

```ts
// Pure terrain math, mirrored by the backend slope_aspect.py (the FE drives the
// map shading; the BE the dashboard value). Kept in sync by their unit tests.

export function decodeTerrarium(r: number, g: number, b: number): number {
  return r * 256 + g + b / 256 - 32768;
}

export function decodeMapbox(r: number, g: number, b: number): number {
  return -10000 + (r * 65536 + g * 256 + b) * 0.1;
}

/** slope (deg) + aspect (deg, 0=N 90=E clockwise) from 5 elevations + spacing (m). */
export function pixelSlopeAspect(
  center: number, north: number, east: number, south: number, west: number, spacing: number,
): { slope: number; aspect: number } {
  void center;
  const dzdx = (east - west) / (2 * spacing);
  const dzdy = (north - south) / (2 * spacing);
  const slope = (Math.atan(Math.hypot(dzdx, dzdy)) * 180) / Math.PI;
  if (dzdx === 0 && dzdy === 0) return { slope: 0, aspect: 0 };
  const aspect = ((Math.atan2(-dzdx, -dzdy) * 180) / Math.PI + 360) % 360;
  return { slope, aspect };
}

/** Web-mercator ground resolution (m/px) at a latitude + zoom for 256px tiles. */
export function metersPerPixel(latDeg: number, zoom: number): number {
  return (40075016.686 * Math.cos((latDeg * Math.PI) / 180)) / (256 * 2 ** zoom);
}

/** Latitude (deg) of the center of tile y at zoom z. */
export function tileCenterLat(y: number, z: number): number {
  const n = Math.PI - (2 * Math.PI * (y + 0.5)) / 2 ** z;
  return (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS (all terrainMath + terrainColors tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/layers/terrainMath.ts frontend/src/layers/terrainMath.test.ts
git commit -m "feat(terrain): DEM decode + slope/aspect math + tests"
```

---

## Task 7: DEM source adapter (Vitest)

**Files:**
- Create: `frontend/src/layers/dem.ts`
- Test: `frontend/src/layers/dem.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/layers/dem.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { getDemSource } from "./dem";

describe("getDemSource", () => {
  it("defaults to free Terrarium with no key", () => {
    const dem = getDemSource();
    expect(dem.encoding).toBe("terrarium");
    expect(dem.tiles[0]).toContain("elevation-tiles-prod");
    expect(dem.maxzoom).toBe(15);
    expect(dem.tileSize).toBe(256);
  });
});
```

(Note: `import.meta.env.VITE_MAPTILER_KEY` is undefined under Vitest, so the free branch is exercised.)

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL (cannot find `./dem`).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/layers/dem.ts`:

```ts
const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined;

export type DemEncoding = "terrarium" | "mapbox";

export interface DemSourceConfig {
  tiles: string[];
  encoding: DemEncoding;
  tileSize: number;
  maxzoom: number;
  attribution: string;
}

/** Free AWS Terrarium by default; MapTiler terrain-RGB when a key is set. */
export function getDemSource(): DemSourceConfig {
  if (MAPTILER_KEY) {
    return {
      tiles: [`https://api.maptiler.com/tiles/terrain-rgb-v2/{z}/{x}/{y}.webp?key=${MAPTILER_KEY}`],
      encoding: "mapbox",
      tileSize: 256,
      maxzoom: 12,
      attribution: "© MapTiler © OpenStreetMap contributors",
    };
  }
  return {
    tiles: ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"],
    encoding: "terrarium",
    tileSize: 256,
    maxzoom: 15,
    attribution: "Elevation: Mapzen/Terrarium, SRTM, USGS",
  };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/layers/dem.ts frontend/src/layers/dem.test.ts
git commit -m "feat(terrain): DEM source adapter (free Terrarium / MapTiler) + test"
```

---

## Task 8: Terrain Web Worker (slope/aspect tiles)

**Files:**
- Create: `frontend/src/layers/terrainWorker.ts`

Manual-verify task (a Web Worker using browser APIs — not unit-tested; its math is covered by Task 6).

- [ ] **Step 1: Write the worker**

Create `frontend/src/layers/terrainWorker.ts`:

```ts
/// <reference lib="webworker" />
import { decodeTerrarium, decodeMapbox, pixelSlopeAspect, metersPerPixel, tileCenterLat } from "./terrainMath";
import { slopeColor, aspectColor } from "./terrainColors";
import type { DemEncoding } from "./dem";

interface Req { id: number; kind: "slope" | "aspect"; z: number; x: number; y: number; demUrl: string; encoding: DemEncoding; }

const TILE = 256;

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

self.onmessage = async (ev: MessageEvent<Req>) => {
  const { id, kind, z, x, y, demUrl, encoding } = ev.data;
  try {
    const url = demUrl.replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`dem ${resp.status}`);
    const bmp = await createImageBitmap(await resp.blob());
    const src = new OffscreenCanvas(TILE, TILE);
    const sctx = src.getContext("2d")!;
    sctx.drawImage(bmp, 0, 0, TILE, TILE);
    const px = sctx.getImageData(0, 0, TILE, TILE).data;

    const decode = encoding === "terrarium" ? decodeTerrarium : decodeMapbox;
    const elev = new Float32Array(TILE * TILE);
    for (let i = 0; i < TILE * TILE; i++) {
      elev[i] = decode(px[i * 4], px[i * 4 + 1], px[i * 4 + 2]);
    }
    const spacing = metersPerPixel(tileCenterLat(y, z), z);

    const out = new ImageData(TILE, TILE);
    const od = out.data;
    const at = (cx: number, cy: number) => elev[Math.min(TILE - 1, Math.max(0, cy)) * TILE + Math.min(TILE - 1, Math.max(0, cx))];
    for (let cy = 0; cy < TILE; cy++) {
      for (let cx = 0; cx < TILE; cx++) {
        const { slope, aspect } = pixelSlopeAspect(
          at(cx, cy), at(cx, cy - 1), at(cx + 1, cy), at(cx, cy + 1), at(cx - 1, cy), spacing,
        );
        const [r, g, b] = hexToRgb(kind === "slope" ? slopeColor(slope) : aspectColor(aspect));
        const o = (cy * TILE + cx) * 4;
        od[o] = r; od[o + 1] = g; od[o + 2] = b; od[o + 3] = 255;
      }
    }
    const dst = new OffscreenCanvas(TILE, TILE);
    dst.getContext("2d")!.putImageData(out, 0, 0);
    const buf = await (await dst.convertToBlob({ type: "image/png" })).arrayBuffer();
    (self as unknown as Worker).postMessage({ id, ok: true, buf }, [buf]);
  } catch (err) {
    (self as unknown as Worker).postMessage({ id, ok: false, error: String(err) });
  }
};
```

- [ ] **Step 2: Verify type check**

Run: `cd frontend && npx tsc -b`
Expected: no errors. (If TS complains about `OffscreenCanvas`/`createImageBitmap`, ensure `tsconfig` lib includes `DOM` — it does for a Vite React app; the `/// <reference lib="webworker" />` covers worker globals.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/layers/terrainWorker.ts
git commit -m "feat(terrain): web worker computes colored slope/aspect tiles"
```

---

## Task 9: Register slope:// and aspect:// protocols

**Files:**
- Create: `frontend/src/layers/terrainProtocol.ts`

Manual-verify task (MapLibre protocol glue).

- [ ] **Step 1: Write the protocol registrar**

Create `frontend/src/layers/terrainProtocol.ts`:

```ts
import type maplibregl from "maplibre-gl";
import type { DemSourceConfig } from "./dem";

let worker: Worker | null = null;
let seq = 0;
const pending = new Map<number, (r: { ok: boolean; buf?: ArrayBuffer; error?: string }) => void>();

function getWorker(): Worker {
  if (!worker) {
    worker = new Worker(new URL("./terrainWorker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (ev) => {
      const cb = pending.get(ev.data.id);
      if (cb) { pending.delete(ev.data.id); cb(ev.data); }
    };
  }
  return worker;
}

function parseTile(url: string): { z: number; x: number; y: number } {
  // e.g. "slope://10/163/395"
  const m = url.split("://")[1].split("/");
  return { z: Number(m[0]), x: Number(m[1]), y: Number(m[2]) };
}

/** Registers slope:// and aspect:// protocols that return colored raster tiles.
 *  Idempotent-ish: call once on map init with the active DEM config. */
export function registerTerrainProtocols(mlgl: typeof maplibregl, dem: DemSourceConfig) {
  const make = (kind: "slope" | "aspect") =>
    (params: { url: string }): Promise<{ data: ArrayBuffer }> =>
      new Promise((resolve, reject) => {
        const { z, x, y } = parseTile(params.url);
        const id = ++seq;
        pending.set(id, (r) => {
          if (r.ok && r.buf) resolve({ data: r.buf });
          else reject(new Error(r.error || "terrain tile failed"));
        });
        getWorker().postMessage({ id, kind, z, x, y, demUrl: dem.tiles[0], encoding: dem.encoding });
      });
  mlgl.addProtocol("slope", make("slope"));
  mlgl.addProtocol("aspect", make("aspect"));
}
```

- [ ] **Step 2: Verify type check**

Run: `cd frontend && npx tsc -b`
Expected: no errors. If MapLibre's `addProtocol` handler type differs in v4.7 (it expects `(requestParameters, abortController) => Promise<GetResourceResponse>`), adjust the callback signature to match the installed `maplibre-gl` types — keep the body identical. Confirm via the types in `node_modules/maplibre-gl`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/layers/terrainProtocol.ts
git commit -m "feat(terrain): register slope:// and aspect:// MapLibre protocols"
```

---

## Task 10: Contours via maplibre-contour

**Files:**
- Create: `frontend/src/layers/contours.ts`

Manual-verify task (external library glue).

- [ ] **Step 1: Write the contour setup**

Create `frontend/src/layers/contours.ts`:

```ts
import mlcontour from "maplibre-contour";
import type maplibregl from "maplibre-gl";
import type { DemSourceConfig } from "./dem";

let demSource: InstanceType<typeof mlcontour.DemSource> | null = null;

/** One-time: register maplibre-contour's protocol over the active DEM. */
export function setupContours(mlgl: typeof maplibregl, dem: DemSourceConfig) {
  if (demSource) return;
  demSource = new mlcontour.DemSource({
    url: dem.tiles[0],
    encoding: dem.encoding,
    maxzoom: dem.maxzoom,
    worker: true,
  });
  demSource.setupMaplibre(mlgl);
}

/** Vector tile URL for the contour source (feet; 40 ft minor / 200 ft index). */
export function contourTilesUrl(): string {
  if (!demSource) throw new Error("setupContours must run first");
  return demSource.contourProtocolUrl({
    multiplier: 3.28084, // meters -> feet
    thresholds: {
      10: [200, 1000],
      12: [80, 400],
      14: [40, 200],
    },
    elevationKey: "ele",
    levelKey: "level",
    contourLayer: "contours",
  });
}
```

- [ ] **Step 2: Verify type check**

Run: `cd frontend && npx tsc -b`
Expected: no errors. If `maplibre-contour` ships its own types with a different shape (e.g. default export vs named `DemSource`), adjust the import to match `node_modules/maplibre-contour` types; keep the option keys (`url`, `encoding`, `maxzoom`, `thresholds`, `multiplier`, `contourLayer`) as documented by the installed version.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/layers/contours.ts
git commit -m "feat(terrain): contour vector tiles via maplibre-contour"
```

---

## Task 11: Legend "wheel" kind (types + component)

**Files:**
- Modify: `frontend/src/layers/types.ts`
- Modify: `frontend/src/components/Legend.tsx`

- [ ] **Step 1: Extend the Legend type**

In `frontend/src/layers/types.ts`, change the `Legend` interface `kind` union from:

```ts
  kind: "swatches" | "gradient" | "none";
```

to:

```ts
  kind: "swatches" | "gradient" | "wheel" | "none";
```

- [ ] **Step 2: Render the wheel**

Replace the contents of `frontend/src/components/Legend.tsx` with:

```tsx
import type { Legend as LegendType } from "../layers/types";
import { ASPECT_COLORS } from "../layers/terrainColors";

function AspectWheel() {
  const a = ASPECT_COLORS;
  const bg = `conic-gradient(${a.N} 0 45deg,${a.NE} 45deg 90deg,${a.E} 90deg 135deg,${a.SE} 135deg 180deg,${a.S} 180deg 225deg,${a.SW} 225deg 270deg,${a.W} 270deg 315deg,${a.NW} 315deg 360deg)`;
  return (
    <div className="legend">
      <span className="aspect-wheel" style={{ background: bg }} aria-label="aspect color wheel" />
      <span className="legend-note">N cool · S warm</span>
    </div>
  );
}

export default function Legend({ legend }: { legend: LegendType }) {
  if (!legend || legend.kind === "none") return null;
  if (legend.kind === "wheel") return <AspectWheel />;
  if (!legend.items?.length) return null;
  return (
    <div className="legend">
      {legend.items.map((it) => (
        <span key={it.label} className="legend-item">
          <span className="legend-swatch" style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
      {legend.note ? <span className="legend-note">{legend.note}</span> : null}
    </div>
  );
}
```

- [ ] **Step 3: Verify type check**

Run: `cd frontend && npx tsc -b`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/layers/types.ts frontend/src/components/Legend.tsx
git commit -m "feat(ui): aspect wheel legend kind"
```

---

## Task 12: Register the terrain layers

**Files:**
- Modify: `frontend/src/layers/registry.ts`

- [ ] **Step 1: Replace the "coming soon" block**

In `frontend/src/layers/registry.ts`, replace the entire `// --- coming soon (disabled previews) ---` block (the three entries: `overlay.slope`, `overlay.hillshade`, `overlay.weather`) with:

```ts
  // --- terrain (Phase 2; draw order bottom->top: hillshade, slope, aspect, contours) ---
  { id: "overlay.hillshade", group: "terrain", kind: "raster-overlay", label: "Hillshade",
    defaultVisible: false, defaultOpacity: 0.45, supportsOpacity: true,
    legend: { kind: "none" } },
  { id: "overlay.slope", group: "terrain", kind: "raster-overlay", label: "Slope angle",
    defaultVisible: false, defaultOpacity: 0.55, supportsOpacity: true,
    legend: { kind: "swatches", items: [
      { color: "#1a9850", label: "0–15" }, { color: "#a6d96a", label: "15–25" },
      { color: "#f1e34d", label: "25–30" }, { color: "#fdae61", label: "30–35" },
      { color: "#d73027", label: "35–45" }, { color: "#7b3294", label: "45+" }] } },
  { id: "overlay.aspect", group: "terrain", kind: "raster-overlay", label: "Aspect",
    defaultVisible: false, defaultOpacity: 0.55, supportsOpacity: true,
    legend: { kind: "wheel" } },
  { id: "overlay.contours", group: "terrain", kind: "vector-overlay", label: "Contours",
    defaultVisible: false, defaultOpacity: 0.8, supportsOpacity: true,
    legend: { kind: "swatches", note: "40 ft / 200 ft index", items: [{ color: "#7a5a3a", label: "contour" }] } },

  // --- coming soon (disabled previews) ---
  { id: "overlay.weather", group: "weather", kind: "data-overlay", label: "Weather / snow",
    providerId: "weather", defaultVisible: false, defaultOpacity: 1, supportsOpacity: false,
    comingSoonPhase: 3 },
```

(The `OVERLAY_LAYERS` / `COMING_SOON_LAYERS` filters at the bottom are unchanged — terrain layers have no `comingSoonPhase`, so they correctly land in `OVERLAY_LAYERS`; only `overlay.weather` stays in "coming soon".)

- [ ] **Step 2: Verify type check**

Run: `cd frontend && npx tsc -b`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/layers/registry.ts
git commit -m "feat(terrain): register hillshade/slope/aspect/contours layers"
```

---

## Task 13: MapView terrain rendering + hover elevation

**Files:**
- Modify: `frontend/src/components/MapView.tsx`

Manual-verify task (the core integration). Apply four edits.

- [ ] **Step 1: Add imports**

After the existing import line `import { activeBasemapId } from "../layers/layerState";` add:

```ts
import { getDemSource } from "../layers/dem";
import { registerTerrainProtocols } from "../layers/terrainProtocol";
import { setupContours, contourTilesUrl } from "../layers/contours";
import { decodeTerrarium, decodeMapbox } from "../layers/terrainMath";
```

- [ ] **Step 2: Extend `OVERLAY_RENDER`**

Replace the `OVERLAY_RENDER` object with this version (adds the four terrain ids; hillshade "opacity" maps to `hillshade-exaggeration`, raster layers to `raster-opacity`, contours to `line-opacity`):

```ts
const OVERLAY_RENDER: Record<string, { layerIds: string[]; opacity?: [string, string][] }> = {
  "overlay.perimeters": {
    layerIds: ["perims-fill", "perims-line"],
    opacity: [["perims-fill", "fill-opacity"], ["perims-line", "line-opacity"]],
  },
  "overlay.fires": { layerIds: ["fires-circle"], opacity: [["fires-circle", "circle-opacity"]] },
  "overlay.gpx": { layerIds: ["gpx-line"], opacity: [["gpx-line", "line-opacity"]] },
  "overlay.savedTrips": { layerIds: ["trips-circle", "trips-label"] },
  "overlay.hillshade": { layerIds: ["hillshade"], opacity: [["hillshade", "hillshade-exaggeration"]] },
  "overlay.slope": { layerIds: ["slope-raster"], opacity: [["slope-raster", "raster-opacity"]] },
  "overlay.aspect": { layerIds: ["aspect-raster"], opacity: [["aspect-raster", "raster-opacity"]] },
  "overlay.contours": { layerIds: ["contour-lines", "contour-labels"], opacity: [["contour-lines", "line-opacity"]] },
};

const DEM = getDemSource();
let terrainProtocolsReady = false;
```

- [ ] **Step 3: Add terrain sources/layers in `addOverlaySources`**

At the END of `addOverlaySources(map)` (just before its closing `}`), append:

```ts
    // --- terrain (Phase 2) ---
    if (!terrainProtocolsReady) {
      registerTerrainProtocols(maplibregl, DEM);
      setupContours(maplibregl, DEM);
      terrainProtocolsReady = true;
    }
    map.addSource("dem", {
      type: "raster-dem", tiles: DEM.tiles, encoding: DEM.encoding,
      tileSize: DEM.tileSize, maxzoom: DEM.maxzoom, attribution: DEM.attribution,
    });
    map.addLayer({ id: "hillshade", type: "hillshade", source: "dem",
      paint: { "hillshade-exaggeration": 0.45 }, layout: { visibility: "none" } });
    map.addSource("slope", { type: "raster", tiles: ["slope://{z}/{x}/{y}"], tileSize: 256, minzoom: 10, maxzoom: 22 });
    map.addLayer({ id: "slope-raster", type: "raster", source: "slope", minzoom: 10,
      paint: { "raster-opacity": 0.55 }, layout: { visibility: "none" } });
    map.addSource("aspect", { type: "raster", tiles: ["aspect://{z}/{x}/{y}"], tileSize: 256, minzoom: 10, maxzoom: 22 });
    map.addLayer({ id: "aspect-raster", type: "raster", source: "aspect", minzoom: 10,
      paint: { "raster-opacity": 0.55 }, layout: { visibility: "none" } });
    map.addSource("contours", { type: "vector", tiles: [contourTilesUrl()], maxzoom: DEM.maxzoom });
    map.addLayer({ id: "contour-lines", type: "line", source: "contours", "source-layer": "contours", minzoom: 10,
      paint: { "line-color": "#7a5a3a", "line-width": ["match", ["get", "level"], 1, 1.4, 0.6], "line-opacity": 0.8 },
      layout: { visibility: "none" } });
    map.addLayer({ id: "contour-labels", type: "symbol", source: "contours", "source-layer": "contours", minzoom: 13,
      filter: ["==", ["get", "level"], 1],
      layout: { "symbol-placement": "line", "text-field": ["concat", ["get", "ele"], " ft"], "text-size": 10,
        "text-font": ["Noto Sans Regular"], visibility: "none" },
      paint: { "text-color": "#5c4530", "text-halo-color": "#fbfaf6", "text-halo-width": 1.2 } });
```

- [ ] **Step 4: Add the hover elevation chip**

(a) Add a ref near the other refs (after `const activeBaseRef = ...`):

```ts
  const hoverElevRef = useRef<HTMLDivElement | null>(null);
```

(b) In the init effect, after the `map.on("mouseleave", "trips-circle", ...)` line, add a mousemove handler that reads the DEM tile under the cursor when a terrain layer is on:

```ts
    map.on("mousemove", (e) => {
      const el = hoverElevRef.current;
      if (!el) return;
      const terrainOn = ["overlay.hillshade", "overlay.slope", "overlay.aspect", "overlay.contours"]
        .some((id) => map.getLayer(OVERLAY_RENDER[id].layerIds[0]) &&
          map.getLayoutProperty(OVERLAY_RENDER[id].layerIds[0], "visibility") === "visible");
      if (!terrainOn) { el.style.display = "none"; return; }
      const m = elevationAtPoint(map, e.point);
      if (m == null) { el.style.display = "none"; return; }
      el.style.display = "block";
      el.style.left = `${e.point.x + 12}px`;
      el.style.top = `${e.point.y + 12}px`;
      el.textContent = `${Math.round(m * 3.28084).toLocaleString()} ft`;
    });
```

(c) Add this helper function inside the component (next to `setVisible`):

```ts
  function elevationAtPoint(map: maplibregl.Map, pt: { x: number; y: number }): number | null {
    const src = map.getSource("dem") as unknown as { _coveringTiles?: unknown };
    void src;
    // Read elevation by sampling the rendered DEM via queryTerrainElevation if available.
    const q = (map as unknown as { queryTerrainElevation?: (l: maplibregl.LngLatLike) => number | null }).queryTerrainElevation;
    if (typeof q === "function") {
      const v = q.call(map, map.unproject([pt.x, pt.y]));
      return v == null ? null : v;
    }
    return null;
  }
  void decodeTerrarium; void decodeMapbox;
```

> Note: MapLibre's `queryTerrainElevation` returns elevation only when 3D terrain is set. Since we use a flat map, this returns null. For a reliable flat-map hover readout, the implementer should instead sample the loaded slope/aspect DEM: keep a small client cache of decoded DEM tiles keyed by z/x/y (populated by a lightweight fetch+decode using `decodeTerrarium`/`decodeMapbox` already imported) and look up the pixel under the cursor. Wire this during manual verification; the chip must show a plausible elevation (compare to the click→dashboard elevation) before this task is considered done.

(d) In the returned JSX, add the chip element after the `<div className="map-overlay-br">…</div>` line:

```tsx
      <div ref={hoverElevRef} className="hover-elev" style={{ display: "none" }} />
```

- [ ] **Step 5: Verify type check + build**

Run: `cd frontend && npx tsc -b && npm run build`
Expected: no type errors; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/MapView.tsx
git commit -m "feat(terrain): render hillshade/slope/aspect/contours + hover elevation"
```

---

## Task 14: PointDashboard slope/aspect display

**Files:**
- Modify: `frontend/src/components/PointDashboard.tsx`

- [ ] **Step 1: Add a slope/aspect value renderer**

In `frontend/src/components/PointDashboard.tsx`, add this component after `ElevationValue`:

```tsx
function SlopeAspectValue({ data }: { data: Record<string, unknown> | null | undefined }) {
  const slope = data?.slope_deg as number | undefined;
  const compass = data?.aspect_compass as string | undefined;
  const bucket = data?.slope_bucket as string | undefined;
  if (slope == null) return null;
  return (
    <div className="point-elev">
      {Math.round(slope)}° · {compass ?? "—"}
      {bucket ? <span className="point-bucket"> · {bucket} band</span> : null}
    </div>
  );
}
```

- [ ] **Step 2: Render it in `SectionCard`**

In `SectionCard`, after the elevation line:

```tsx
      {s.layer_id === "elevation" && s.status === "ok" ? <ElevationValue data={s.data} /> : null}
```

add:

```tsx
      {s.layer_id === "slope_aspect" && s.status === "ok" ? <SlopeAspectValue data={s.data} /> : null}
```

- [ ] **Step 3: Verify type check**

Run: `cd frontend && npx tsc -b`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PointDashboard.tsx
git commit -m "feat(ui): slope/aspect value in the This-point dashboard"
```

---

## Task 15: Styles (hover chip, aspect wheel, contour swatch)

**Files:**
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Append styles**

Append to `frontend/src/index.css`:

```css
/* --- terrain --- */
.hover-elev {
  position: absolute; z-index: 6; pointer-events: none;
  background: #1f241fdd; color: #fbfaf6; font-size: 11px; font-weight: 600;
  padding: 2px 6px; border-radius: 4px; white-space: nowrap;
}
.aspect-wheel {
  width: 34px; height: 34px; border-radius: 50%; display: inline-block;
  box-shadow: inset 0 0 0 1px rgba(0,0,0,.15);
}
.point-bucket { color: #8a8575; font-weight: 400; }
```

- [ ] **Step 2: Verify the build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "style: terrain hover chip + aspect wheel legend"
```

---

## Task 16: Docs + final verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document terrain layers**

In `README.md`, update the "Map layers" bullet (added in Phase 1) to mention terrain — append this sentence to it:

```markdown
  Terrain layers (Phase 2): hillshade, avalanche slope-angle shading, aspect, and on-the-fly contours, all from free elevation tiles (no key); clicking a point also reports slope° and aspect.
```

- [ ] **Step 2: Commit docs**

```bash
git add README.md
git commit -m "docs: note Phase 2 terrain layers"
```

- [ ] **Step 3: Full backend suite**

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/ -q`
Expected: ALL pass (Phase 1 + slope_aspect + updated providers tests).

- [ ] **Step 4: Frontend unit tests + build**

Run: `cd frontend && npm test && npm run build`
Expected: Vitest all pass; `npm run build` succeeds.

- [ ] **Step 5: Manual verification (browser)**

Start both servers (backend on 8000 via the venv uvicorn; frontend `npm run dev`). Then:
1. Open the floating **Layers** panel → the **Terrain** group now shows Hillshade, Slope angle, Aspect, Contours (no longer "coming soon").
2. Zoom to mountainous terrain (≥ z10). Toggle **Hillshade** → relief appears. Toggle **Slope angle** → avalanche ramp shading; the 30–45° bands read orange/red. Toggle **Aspect** → compass-hued shading; legend shows the wheel. Toggle **Contours** → labeled isolines. Opacity sliders work on each.
3. Hover over terrain (with a terrain layer on) → the elevation chip tracks the cursor and shows a plausible value.
4. Click a point → "This point" shows **slope° + aspect** (e.g. "38° · NE · 35–45° band") alongside elevation.
5. **Coexistence:** basemaps still switch; Phase 1 overlays (fires/perimeters/GPX/trips) still render; logging in + Run condition check still works.

Confirm each. Fix any failures before declaring done.

- [ ] **Step 6: Final commit (only if fixes were needed)**

```bash
git add -A
git commit -m "fix: address issues from Phase 2 manual verification"
```

---

## Self-Review (plan author)

**Spec coverage:** DEM adapter → Task 7; hillshade → Task 13; slope/aspect compute (worker+protocol) → Tasks 5,6,8,9,13; contours → Tasks 10,13; hover elevation → Task 13; aspect wheel legend → Task 11; terrain registry → Task 12; backend SlopeAspectProvider + math → Tasks 1,2,3; dashboard display → Task 14; Vitest → Tasks 4–7; coexistence/regression → Tasks 3 (full suite), 16 (full suite + manual); config (free DEM) → Task 7; docs → Task 16.

**Type consistency:** `compute_slope_aspect`/`slope_bucket_label`/`aspect_compass` (Py) consistent across Tasks 1–3; `SLOPE_BUCKETS`/`ASPECT_COLORS`/`slopeColor`/`aspectColor` (TS) consistent Tasks 5,8,11; `pixelSlopeAspect`/`decodeTerrarium`/`decodeMapbox`/`metersPerPixel`/`tileCenterLat` consistent Tasks 6,8; `getDemSource`/`DemSourceConfig`/`DemEncoding` consistent Tasks 7,8,9,10,13; `registerTerrainProtocols`/`setupContours`/`contourTilesUrl` consistent Tasks 9,10,13; registry ids (`overlay.hillshade/slope/aspect/contours`) consistent Tasks 12,13; MapLibre layer ids (`hillshade`,`slope-raster`,`aspect-raster`,`contour-lines`,`contour-labels`) consistent in Task 13's `OVERLAY_RENDER` + `addLayer`.

**Risk notes (flagged for manual verification, not placeholders):** the two external-library touchpoints (MapLibre `addProtocol` handler signature in Task 9; `maplibre-contour` `DemSource` API in Task 10) and the worker browser-API glue (Task 8) and the flat-map hover-elevation sampling (Task 13 step 4c) carry the real implementation risk; each has a concrete starting implementation plus an explicit manual-verify gate, since they can't be unit-tested and depend on installed library versions.
