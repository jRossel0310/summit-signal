# Client-Side DEM Slope/Aspect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute the point-dashboard "Slope & aspect" value on the client from the on-device DEM, and delete the backend Open-Meteo provider, so the card never calls a rate-limited API.

**Architecture:** A new `pointSample.ts` owns the DEM tile cache (lifted from MapView) and exposes `elevationAtM` (hover reuses it) + `async sampleSlopeAspect`. `App.inspectPoint` computes slope/aspect concurrently with the backend point-context and splices the section in after `elevation`. The backend `SlopeAspectProvider` is removed.

**Tech Stack:** React + TypeScript + Vite + MapLibre GL (frontend, Vitest); FastAPI + pytest (backend).

**Spec:** `docs/superpowers/specs/2026-06-16-slope-aspect-client-dem-design.md`

---

## Setup (once, before frontend tasks)

The worktree's `frontend/node_modules` is gitignored and absent. Install before running any frontend command:

```bash
cd frontend && npm install
```

**Frontend commands** (run from `frontend/`): test a file `npx vitest run src/layers/<file>`; typecheck `npx tsc -b`; build `npm run build`.
**Backend commands** (run from `backend/`): `"C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/ -q` (shared venv supplies pytest + deps; `app` is imported from the worktree cwd).

Implement tasks **in order** (1→5). Frontend stays consistent at every commit; the backend provider is removed last.

---

## Task 1: Compass + slope-band label helpers (terrainMath.ts)

Pure helpers mirroring the backend's compass/bands, so the displayed labels are unchanged. `pointSample.ts` (Task 2) imports them.

**Files:**
- Modify: `frontend/src/layers/terrainMath.ts`
- Test: `frontend/src/layers/terrainMath.test.ts`

- [ ] **Step 1: Add the failing tests** — append to `frontend/src/layers/terrainMath.test.ts`:

```ts
import {
  decodeTerrarium, decodeMapbox, pixelSlopeAspect, metersPerPixel,
  aspectCompass, slopeBucketLabel,
} from "./terrainMath";

describe("aspectCompass", () => {
  it("maps cardinals, diagonals, and wraps", () => {
    expect(aspectCompass(0)).toBe("N");
    expect(aspectCompass(90)).toBe("E");
    expect(aspectCompass(180)).toBe("S");
    expect(aspectCompass(270)).toBe("W");
    expect(aspectCompass(45)).toBe("NE");
    expect(aspectCompass(360)).toBe("N");
    expect(aspectCompass(338)).toBe("N");
  });
});

describe("slopeBucketLabel", () => {
  it("maps band boundaries (en-dash labels)", () => {
    expect(slopeBucketLabel(14.9)).toBe("0–15°");
    expect(slopeBucketLabel(15)).toBe("15–25°");
    expect(slopeBucketLabel(32)).toBe("30–35°");
    expect(slopeBucketLabel(40)).toBe("35–45°");
    expect(slopeBucketLabel(45)).toBe("45°+");
    expect(slopeBucketLabel(60)).toBe("45°+");
  });
});
```

> Note: the existing top-of-file line `import { decodeTerrarium, decodeMapbox, pixelSlopeAspect, metersPerPixel } from "./terrainMath";` and the new import above will both exist. Replace the existing import line with the new combined import (which adds `aspectCompass, slopeBucketLabel`) rather than duplicating — keep a single import from `"./terrainMath"`.

- [ ] **Step 2: Run the tests; verify they fail**

Run: `cd frontend && npx vitest run src/layers/terrainMath.test.ts`
Expected: FAIL — `aspectCompass`/`slopeBucketLabel` are not exported.

- [ ] **Step 3: Implement the helpers** — append to `frontend/src/layers/terrainMath.ts`:

```ts
const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

/** 8-point compass for an aspect bearing (deg, 0=N clockwise). */
export function aspectCompass(deg: number): string {
  const d = ((deg % 360) + 360) % 360;
  return COMPASS[Math.round(d / 45) % 8];
}

const SLOPE_BANDS: [number, number | null, string][] = [
  [0, 15, "0–15°"], [15, 25, "15–25°"], [25, 30, "25–30°"],
  [30, 35, "30–35°"], [35, 45, "35–45°"], [45, null, "45°+"],
];

/** Avalanche-standard slope band label for a slope angle (deg). */
export function slopeBucketLabel(deg: number): string {
  for (const [lo, hi, label] of SLOPE_BANDS) {
    if (deg >= lo && (hi === null || deg < hi)) return label;
  }
  return SLOPE_BANDS[SLOPE_BANDS.length - 1][2];
}
```

> The labels use the en-dash `–` (U+2013) to match what the card renders today.

- [ ] **Step 4: Run the tests; verify they pass**

Run: `cd frontend && npx vitest run src/layers/terrainMath.test.ts`
Expected: PASS (all describes green).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/layers/terrainMath.ts frontend/src/layers/terrainMath.test.ts
git commit -m "feat(terrain): aspectCompass + slopeBucketLabel helpers"
```

---

## Task 2: On-device DEM sampler (pointSample.ts)

The core. Owns the DEM tile cache + pure sampling math + the public `elevationAtM` / `sampleSlopeAspect`. Pure functions are unit-tested; the fetch/decode path (canvas-only) is covered by manual testing and exercised via a primed-cache seam.

**Files:**
- Create: `frontend/src/layers/pointSample.ts`
- Test: `frontend/src/layers/pointSample.test.ts`

- [ ] **Step 1: Write the failing tests** — create `frontend/src/layers/pointSample.test.ts`:

```ts
import { describe, it, expect, beforeEach } from "vitest";
import {
  decodeTileFromImageData, lngLatToTilePixel, slopeAspectAt, sampleSlopeAspect,
  __primeTileForTest, __resetTilesForTest, type SlopeAspectSample,
} from "./pointSample";

const TILE = 256;

function flatTile(elev: number): Float32Array {
  return new Float32Array(TILE * TILE).fill(elev);
}
// Elevation rises toward the EAST (increasing x) -> terrain faces downhill WEST.
function eastRisingTile(): Float32Array {
  const a = new Float32Array(TILE * TILE);
  for (let y = 0; y < TILE; y++) for (let x = 0; x < TILE; x++) a[y * TILE + x] = x * 10;
  return a;
}

beforeEach(() => __resetTilesForTest());

describe("decodeTileFromImageData", () => {
  it("decodes terrarium sea level from RGBA bytes", () => {
    const data = new Uint8ClampedArray([128, 0, 0, 255, 128, 0, 0, 255]);
    const arr = decodeTileFromImageData(data, "terrarium");
    expect(arr.length).toBe(2);
    expect(arr[0]).toBeCloseTo(0, 5);
  });
});

describe("lngLatToTilePixel", () => {
  it("keeps pixel coords within [0, TILE)", () => {
    const { px, py } = lngLatToTilePixel(-105.0, 40.0, 12);
    expect(px).toBeGreaterThanOrEqual(0);
    expect(px).toBeLessThan(TILE);
    expect(py).toBeGreaterThanOrEqual(0);
    expect(py).toBeLessThan(TILE);
  });
});

describe("slopeAspectAt", () => {
  it("flat tile -> 0 slope, 0–15 band", () => {
    const r = slopeAspectAt(flatTile(1000), 100, 100, 40, 12);
    expect(r.slope_deg).toBe(0);
    expect(r.slope_bucket).toBe("0–15°");
  });
  it("east-rising tile -> west-facing aspect", () => {
    const r = slopeAspectAt(eastRisingTile(), 100, 100, 40, 12);
    expect(r.slope_deg).toBeGreaterThan(0);
    expect(r.aspect_compass).toBe("W");
  });
  it("clamps edge pixels (no NaN at a tile border)", () => {
    const r = slopeAspectAt(eastRisingTile(), 0, 255, 40, 12);
    expect(Number.isFinite(r.slope_deg)).toBe(true);
    expect(Number.isFinite(r.aspect_deg)).toBe(true);
  });
});

describe("sampleSlopeAspect", () => {
  it("computes from a primed tile without fetching", async () => {
    const { tx, ty } = lngLatToTilePixel(-105.0, 40.0, 12);
    __primeTileForTest(12, tx, ty, eastRisingTile());
    const r = await sampleSlopeAspect(-105.0, 40.0);
    expect(r).not.toBeNull();
    expect((r as SlopeAspectSample).aspect_compass).toBe("W");
  });
});
```

- [ ] **Step 2: Run the tests; verify they fail**

Run: `cd frontend && npx vitest run src/layers/pointSample.test.ts`
Expected: FAIL — module `./pointSample` does not exist.

- [ ] **Step 3: Implement the module** — create `frontend/src/layers/pointSample.ts`:

```ts
// On-device DEM point sampling: shared tile cache + elevation/slope-aspect at a
// coordinate. Lifted from MapView's hover reader; the single source for point
// elevation queries (hover readout + dashboard slope/aspect). No metered API.
import { getDemSource, type DemEncoding } from "./dem";
import {
  decodeTerrarium, decodeMapbox, pixelSlopeAspect, metersPerPixel,
  aspectCompass, slopeBucketLabel,
} from "./terrainMath";

const DEM = getDemSource();
const TILE = 256;
const SAMPLE_Z = Math.min(DEM.maxzoom, 12);
const CACHE_MAX = 256;

export interface SlopeAspectSample {
  slope_deg: number;
  aspect_deg: number;
  aspect_compass: string;
  slope_bucket: string;
}

const tiles = new Map<string, Float32Array | "error">();
const inflight = new Map<string, Promise<Float32Array | null>>();

const tileKey = (z: number, x: number, y: number) => `${z}/${x}/${y}`;

/** RGBA ImageData bytes -> Float32Array of elevations (m). Pure; canvas-free. */
export function decodeTileFromImageData(data: Uint8ClampedArray, encoding: DemEncoding): Float32Array {
  const decode = encoding === "terrarium" ? decodeTerrarium : decodeMapbox;
  const out = new Float32Array(data.length / 4);
  for (let i = 0; i < out.length; i++) out[i] = decode(data[i * 4], data[i * 4 + 1], data[i * 4 + 2]);
  return out;
}

function evict() {
  while (tiles.size > CACHE_MAX) {
    const oldest = tiles.keys().next().value;
    if (oldest === undefined) break;
    tiles.delete(oldest);
  }
}

async function ensureTile(z: number, x: number, y: number): Promise<Float32Array | null> {
  const key = tileKey(z, x, y);
  const cached = tiles.get(key);
  if (cached instanceof Float32Array) return cached;
  if (cached === "error") return null;
  const existing = inflight.get(key);
  if (existing) return existing;
  const url = DEM.tiles[0].replace("{z}", String(z)).replace("{x}", String(x)).replace("{y}", String(y));
  const p = (async () => {
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error("dem tile http " + r.status);
      const bmp = await createImageBitmap(await r.blob());
      const c = document.createElement("canvas");
      c.width = TILE; c.height = TILE;
      const cx = c.getContext("2d")!;
      cx.drawImage(bmp, 0, 0, TILE, TILE);
      const arr = decodeTileFromImageData(cx.getImageData(0, 0, TILE, TILE).data, DEM.encoding);
      tiles.set(key, arr); evict();
      return arr;
    } catch {
      tiles.set(key, "error");
      return null;
    } finally {
      inflight.delete(key);
    }
  })();
  inflight.set(key, p);
  return p;
}

function cachedTile(z: number, x: number, y: number): Float32Array | null {
  const cached = tiles.get(tileKey(z, x, y));
  if (cached instanceof Float32Array) return cached;
  if (cached === undefined) void ensureTile(z, x, y); // warm it; ignore the promise
  return null;
}

/** Fractional web-mercator tile + clamped pixel for a coord at zoom z (256px tiles). */
export function lngLatToTilePixel(lng: number, lat: number, z: number) {
  const n = 2 ** z;
  const xf = ((lng + 180) / 360) * n;
  const latRad = (lat * Math.PI) / 180;
  const yf = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
  const tx = Math.floor(xf), ty = Math.floor(yf);
  const px = Math.min(TILE - 1, Math.max(0, Math.floor((xf - tx) * TILE)));
  const py = Math.min(TILE - 1, Math.max(0, Math.floor((yf - ty) * TILE)));
  return { tx, ty, px, py };
}

/** Slope/aspect from a decoded tile at pixel (px,py). Clamps to [1, TILE-2] so the
 *  3x3 neighbourhood stays in-tile. Pure. */
export function slopeAspectAt(tile: Float32Array, px: number, py: number, lat: number, z: number): SlopeAspectSample {
  const cx = Math.min(TILE - 2, Math.max(1, px));
  const cy = Math.min(TILE - 2, Math.max(1, py));
  const at = (x: number, y: number) => tile[y * TILE + x];
  const spacing = metersPerPixel(lat, z);
  const { slope, aspect } = pixelSlopeAspect(
    at(cx, cy), at(cx, cy - 1), at(cx + 1, cy), at(cx, cy + 1), at(cx - 1, cy), spacing,
  );
  return {
    slope_deg: Math.round(slope * 10) / 10,
    aspect_deg: Math.round(aspect * 10) / 10,
    aspect_compass: aspectCompass(aspect),
    slope_bucket: slopeBucketLabel(slope),
  };
}

/** Best-effort elevation (m) at a coord from cached DEM tiles; null if not loaded. */
export function elevationAtM(lng: number, lat: number): number | null {
  const { tx, ty, px, py } = lngLatToTilePixel(lng, lat, SAMPLE_Z);
  const tile = cachedTile(SAMPLE_Z, tx, ty);
  return tile ? tile[py * TILE + px] : null;
}

/** Slope/aspect at a coord from the on-device DEM; null if the tile can't load. */
export async function sampleSlopeAspect(lng: number, lat: number): Promise<SlopeAspectSample | null> {
  try {
    const { tx, ty, px, py } = lngLatToTilePixel(lng, lat, SAMPLE_Z);
    const tile = await ensureTile(SAMPLE_Z, tx, ty);
    if (!tile) return null;
    return slopeAspectAt(tile, px, py, lat, SAMPLE_Z);
  } catch {
    return null;
  }
}

// --- test seam (used only by pointSample.test.ts; no fetch/canvas in tests) ---
export function __primeTileForTest(z: number, x: number, y: number, arr: Float32Array): void {
  tiles.set(tileKey(z, x, y), arr);
}
export function __resetTilesForTest(): void { tiles.clear(); inflight.clear(); }
```

> `dem.ts` currently has `export type DemEncoding = "terrarium" | "mapbox";` — import it as shown. If `DemEncoding` is not exported there, add `export` to that type in `dem.ts` as part of this step.

- [ ] **Step 4: Run the tests; verify they pass**

Run: `cd frontend && npx vitest run src/layers/pointSample.test.ts`
Expected: PASS (decode, tile/pixel, slopeAspectAt flat/east/edge, sampleSlopeAspect primed).

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc -b`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/layers/pointSample.ts frontend/src/layers/pointSample.test.ts frontend/src/layers/dem.ts
git commit -m "feat(terrain): on-device DEM point sampler (elevation + slope/aspect)"
```

---

## Task 3: MapView uses the shared sampler (remove in-file hover cache)

Replace MapView's private DEM hover cache with the shared `elevationAtM`. Behaviour identical; MapView shrinks.

**Files:**
- Modify: `frontend/src/components/MapView.tsx`

- [ ] **Step 1: Swap the import** — in `frontend/src/components/MapView.tsx`, replace:

```ts
import { decodeTerrarium, decodeMapbox } from "../layers/terrainMath";
```

with:

```ts
import { elevationAtM } from "../layers/pointSample";
```

- [ ] **Step 2: Delete the in-file hover cache** — remove these now-unused declarations (the `const DEM = getDemSource();` line and everything else stays):
  - `const HOVER_TILE = 256;`
  - `const HOVER_CACHE_MAX = 256;`
  - `const demHoverTiles = new Map<...>();`
  - the entire `function loadHoverTile(...) { ... }`
  - the entire `function hoverElevationM(...) { ... }`

  (These are the block currently at lines ~42–86, between `let terrainProtocolsReady = false;` and the `interface Props` declaration. Keep `const DEM = getDemSource();` and `let terrainProtocolsReady = false;`.)

- [ ] **Step 3: Call the shared sampler in mousemove** — in the `map.on("mousemove", ...)` handler, replace:

```ts
      const m = hoverElevationM(e.lngLat.lng, e.lngLat.lat);
```

with:

```ts
      const m = elevationAtM(e.lngLat.lng, e.lngLat.lat);
```

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && npx tsc -b && npm run build`
Expected: exit 0, build succeeds, no unused-symbol errors (confirms `decodeTerrarium`/`decodeMapbox` and the removed funcs are no longer referenced).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/MapView.tsx
git commit -m "refactor(map): hover elevation uses shared pointSample.elevationAtM"
```

---

## Task 4: App injects client slope/aspect into the point dashboard

`inspectPoint` computes slope/aspect concurrently with the backend point-context and splices the section in after `elevation` (replacing any backend-provided one).

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add imports** — in `frontend/src/App.tsx`:
  - Change `import type { LayerStateMap, SelectionResult } from "./layers/types";` to:

```ts
import type { LayerStateMap, SelectionResult, PointSection } from "./layers/types";
```

  - Add (near the other `./layers` imports):

```ts
import { sampleSlopeAspect, type SlopeAspectSample } from "./layers/pointSample";
```

- [ ] **Step 2: Add the merge helper** — add this module-level function (outside `App`, e.g. just above `export default function App()`):

```ts
// Replace any backend slope_aspect section with the on-device DEM value, placed
// right after the elevation section so the card order is unchanged.
function withSlopeAspect(sections: PointSection[], sa: SlopeAspectSample | null): PointSection[] {
  const rest = sections.filter((s) => s.layer_id !== "slope_aspect");
  const section: PointSection = sa
    ? {
        layer_id: "slope_aspect", title: "Slope & aspect", status: "ok", data: sa, message: null,
        source: { name: "On-device DEM (Mapzen/Terrarium · SRTM/USGS)", url: null, timestamp: new Date().toISOString() },
      }
    : {
        layer_id: "slope_aspect", title: "Slope & aspect", status: "empty", data: null,
        message: "No terrain data at this point", source: null,
      };
  const elevIdx = rest.findIndex((s) => s.layer_id === "elevation");
  const at = elevIdx >= 0 ? elevIdx + 1 : 0;
  return [...rest.slice(0, at), section, ...rest.slice(at)];
}
```

- [ ] **Step 3: Compute concurrently and merge in `inspectPoint`** — replace the `try { ... }` block inside `inspectPoint` (the part that calls `api.pointContext` and sets the result) with:

```ts
    try {
      const [res, sa] = await Promise.all([
        api.pointContext(lat, lon, enabledDataProviderIds(layerState)),
        sampleSlopeAspect(lon, lat),
      ]);
      const merged: SelectionResult = { ...res, sections: withSlopeAspect(res.sections, sa) };
      pointCacheRef.current.set(key, merged);
      setPointResult(merged);
    } catch (e) {
      setPointError((e as Error).message);
    } finally {
      setPointLoading(false);
    }
```

  (Leave the cache-hit early return and the `setPointLoading(true)` lines above it unchanged.)

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && npx tsc -b && npm run build`
Expected: exit 0.

- [ ] **Step 5: Manual smoke (note for the reviewer)**

With backend + frontend running: click a mountainous point — the "Slope & aspect" card shows `NN° · <compass> · <band> band` sourced "On-device DEM…", with no `429`; rapid clicks never error; click open water — card shows "No terrain data at this point". Freeze/thaw's aspect note still appears.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(point): slope/aspect computed on-device from the DEM"
```

---

## Task 5: Remove the backend SlopeAspectProvider

The client now owns slope/aspect; delete the Open-Meteo-backed provider and update its tests.

**Files:**
- Modify: `backend/app/providers/registry.py`
- Delete: `backend/app/providers/slope_aspect.py`
- Delete: `backend/tests/test_slope_aspect.py`
- Modify: `backend/tests/test_providers.py`

- [ ] **Step 1: Remove from the registry** — in `backend/app/providers/registry.py`:
  - Delete the import line: `from .slope_aspect import SlopeAspectProvider`
  - Delete the list entry line: `    SlopeAspectProvider(),`

- [ ] **Step 2: Delete the provider and its dedicated test**

```bash
git rm backend/app/providers/slope_aspect.py backend/tests/test_slope_aspect.py
```

- [ ] **Step 3: Update the two registry assertions** — in `backend/tests/test_providers.py`:
  - In `test_select_includes_always_on_by_default`, delete the line:

```python
    assert "slope_aspect" in ids   # always-on via SlopeAspectProvider
```

  - Replace the body of `test_select_includes_requested` with a still-existing toggle-gated provider:

```python
def test_select_includes_requested():
    ids = [p.id for p in registry.select_providers(["aqi"])]
    assert "aqi" in ids and "elevation" in ids
```

- [ ] **Step 4: Run the backend suite; verify green**

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/ -q`
Expected: PASS (no `slope_aspect` import errors; point-context tests still pass — they never asserted a slope_aspect section). Note the new passing count (was 89; `test_slope_aspect.py`'s ~8 tests are gone).

- [ ] **Step 5: Confirm no dangling references**

Run: `cd backend && grep -rn "slope_aspect\|SlopeAspectProvider" app/ tests/ || echo "clean"`
Expected: `clean` (no matches).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(providers): remove Open-Meteo slope/aspect provider (now client-side)"
```

---

## Final integration verification

- [ ] **Frontend full suite + build**

Run: `cd frontend && npx vitest run && npx tsc -b && npm run build`
Expected: all tests pass, exit 0.

- [ ] **Backend full suite**

Run: `cd backend && "C:/Users/jacob/summit-signal/backend/.venv/Scripts/python.exe" -m pytest tests/ -q`
Expected: all pass.

- [ ] **Coexistence check** — confirm the condition-check pipeline is untouched:

Run: `git diff --name-only main...HEAD`
Expected: only `frontend/src/layers/{terrainMath,terrainMath.test,pointSample,pointSample.test,dem}.ts`, `frontend/src/components/MapView.tsx`, `frontend/src/App.tsx`, `backend/app/providers/{registry.py,slope_aspect.py(del)}`, `backend/tests/{test_providers.py,test_slope_aspect.py(del)}`, and the two `docs/superpowers/...` files. No connector/pipeline/checks files.

- [ ] **Manual end-to-end** — backend + frontend up: rapid-click mountainous points (slope/aspect fills from DEM, no `429`), open water (calm "No terrain data"), confirm hover elevation readout still works and freeze/thaw aspect note still renders.
