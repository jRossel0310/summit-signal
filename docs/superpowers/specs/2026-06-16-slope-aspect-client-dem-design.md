# Client-Side DEM Slope/Aspect — Design

**Date:** 2026-06-16
**Status:** Approved (design)
**Topic:** Source the "Slope & aspect" point-dashboard value from the on-device DEM instead of the Open-Meteo elevation API.

---

## 1. Problem

The "Slope & aspect" card is the only thing in the point dashboard that calls Open-Meteo's free **elevation** API. `SlopeAspectProvider` ([backend/app/providers/slope_aspect.py](../../../backend/app/providers/slope_aspect.py)) samples 5 elevations (center + N/E/S/W, 50 m apart) on **every** map click. Because:

- there is one uncached call per clicked point (the shared HTTP client has no retry/backoff),
- the aggregator cache only helps on exact repeats (keyed to lat/lon at ~11 m),
- Phase 3's concurrent aggregator fires Snow (also Open-Meteo) and an Elevation fallback (USGS → Open-Meteo) alongside it,

rapid clicking trips Open-Meteo's per-IP rate limit and the card shows `429 Too Many Requests`.

## 2. Key insight

The client already has everything needed to compute slope/aspect locally:

- [frontend/src/components/MapView.tsx](../../../frontend/src/components/MapView.tsx) `loadHoverTile()` / `hoverElevationM()` already fetch a DEM tile and decode **all** pixels into a cached `Float32Array` of elevations (FIFO cache, 256 tiles) — this powers the hover elevation readout.
- [frontend/src/layers/terrainMath.ts](../../../frontend/src/layers/terrainMath.ts) `pixelSlopeAspect()` already computes slope+aspect from 5 elevations (it drives the map shading), and `metersPerPixel()` gives the ground spacing.

So slope/aspect can be derived from the **same DEM tiles the map already loads** — no metered API, and the value is consistent with the hillshade the user sees.

## 3. Goal / non-goals

**Goal:** The "Slope & aspect" card is computed entirely on the client from the DEM. No request to a rate-limited API is ever on its path. Behaviour and appearance are otherwise unchanged.

**Non-goals (kept exactly as-is):**
- **Elevation card** stays on USGS EPQS (authoritative point elevation); its rare Open-Meteo fallback is untouched.
- **Snow** stays on Open-Meteo (different endpoint, not the cause of the 429s).
- The Phase 2 slope/aspect **map raster overlays** are already client-side (the worker) — unchanged.
- The **condition-check pipeline** is untouched (coexistence requirement, as in every prior phase).

## 4. Approach (chosen)

**Pure client-side; remove the backend provider.** Compute slope/aspect from the on-device DEM, delete `SlopeAspectProvider`, and inject the computed `slope_aspect` section into the point-context result on the client. (Rejected alternatives: keeping the Open-Meteo provider as a fallback — keeps the rate-limited path alive; using MapLibre `queryTerrainElevation` — only works when 3D terrain is toggled on, while this card is always-on.)

## 5. Architecture & data flow

Slope/aspect becomes a client-side, terrain-derived value (it belongs with the terrain engine, which already lives on the client). The backend no longer sources it.

```
click → App.inspectPoint(lat, lon)
          ├─ api.pointContext(...)          → sections WITHOUT slope_aspect
          └─ sampleSlopeAspect(lon, lat)    → {slope_deg, aspect_deg, aspect_compass, slope_bucket} | null
        merge: splice slope_aspect section in right after `elevation`
        setPointResult(merged)   → PointDashboard renders identically;
                                    freeze_thaw aspect-note still finds aspect_compass
```

The two fetches run **concurrently** (`Promise.all`); since the backend point-context is normally the slower of the two, the DEM sample adds ~no latency. The merged result is set once (so freeze/thaw's aspect note is present from the first render, no flash) and stored in the existing `pointCacheRef`.

## 6. Components / files

### 6.1 New — `frontend/src/layers/pointSample.ts`

Owns the DEM tile fetch/decode/cache (lifted out of MapView) and is the single source for point elevation sampling. Module-level singleton cache shared by hover and slope sampling.

- `tileCache: Map<string, Float32Array | "error">` — decoded tiles (elevation in metres), FIFO-evicted at 256 entries (preserves current `HOVER_CACHE_MAX`).
- `inflight: Map<string, Promise<Float32Array | null>>` — de-dupes concurrent loads of the same tile.
- `ensureTile(z, x, y): Promise<Float32Array | null>` — returns a decoded tile, awaiting a fetch+decode if needed; resolves `null` on fetch/decode failure (caches `"error"` so it isn't retried in a tight loop). Decoding mirrors the current MapView logic (`createImageBitmap` → canvas → `decodeTerrarium`/`decodeMapbox`).
- `cachedTile(z, x, y): Float32Array | null` — sync; returns a decoded tile if present, else kicks off `ensureTile` (fire-and-forget) and returns `null`. Used by hover.
- `elevationAtM(lng, lat): number | null` — sync, best-effort (uses `cachedTile`). MapView's hover imports this; behaviour identical to today's `hoverElevationM`.
- `async sampleSlopeAspect(lng, lat): Promise<SlopeAspectSample | null>` — the dashboard entry point (detailed in §7).

`SlopeAspectSample = { slope_deg: number; aspect_deg: number; aspect_compass: string; slope_bucket: string }`.

The module imports `getDemSource()` from `./dem` and the decoders + math from `./terrainMath`. It depends on no React/MapLibre state.

### 6.2 Edit — `frontend/src/layers/terrainMath.ts`

Add two pure functions mirroring the backend's `_COMPASS` / `_BUCKETS` (so the displayed labels are unchanged):

- `aspectCompass(deg): string` — 8-point compass (`["N","NE","E","SE","S","SW","W","NW"]`, `(deg % 360)/45` rounded).
- `slopeBucketLabel(deg): string` — bands `0–15°, 15–25°, 25–30°, 30–35°, 35–45°, 45°+` (using the exact en-dash labels the card shows today).

### 6.3 Edit — `frontend/src/components/MapView.tsx`

Replace the in-file hover cache (`demHoverTiles`, `loadHoverTile`, `hoverElevationM`, `HOVER_TILE`, `HOVER_CACHE_MAX`, the `decode*` import) with a single import of `elevationAtM` from `./pointSample`. The `mousemove` handler calls `elevationAtM(lng, lat)` instead of `hoverElevationM`. Net: MapView shrinks; hover behaviour is identical.

### 6.4 Edit — `frontend/src/App.tsx`

In `inspectPoint(lat, lon)`:
- run `api.pointContext(...)` and `sampleSlopeAspect(lon, lat)` concurrently (`Promise.all`; the sampler never throws — it resolves `null` on failure);
- build the `slope_aspect` `PointSection` (§8) from the sample;
- splice it into `res.sections` immediately after the `elevation` section (or at the front if no elevation section is present);
- `setPointResult(merged)` and cache the merged result under the existing key.

(The cache-hit early return is unchanged — a cached merged result already contains slope/aspect.)

### 6.5 Backend — remove the provider

- `backend/app/providers/registry.py`: remove `SlopeAspectProvider` from `_ALL` and its import.
- Delete `backend/app/providers/slope_aspect.py`.
- Remove the provider's unit test (the slope/aspect math is now covered on the FE by `terrainMath` tests). Confirm no other module imports `slope_aspect` (the condition-check pipeline does not — providers are point-context only).

## 7. The sampler algorithm (`sampleSlopeAspect`)

Sampling zoom **`z = min(DEM.maxzoom, 12)`** — the same zoom the hover readout uses, so tiles are shared and warm. At mid-latitudes z12 is ~28 m/pixel; the 1-pixel-each-side gradient spans ~57 m, close to the previous backend 50 m spacing and stable (not jittery with map zoom).

1. Convert `(lng, lat)` → fractional web-mercator tile coords `(xf, yf)` at `z`; `tx = floor(xf)`, `ty = floor(yf)`.
2. Pixel within the 256-px tile: `px = floor((xf - tx) * 256)`, `py = floor((yf - ty) * 256)`.
3. **Clamp `px, py` to `[1, 254]`** so the 3×3 neighbourhood stays inside one tile. The ≤1-pixel (≤~28 m) nudge at a tile edge is negligible for a slope estimate and avoids any multi-tile fetch — every query needs exactly one tile.
4. `tile = await ensureTile(z, tx, ty)`; if `null`, return `null`.
5. Read elevations: `center = tile[py*256+px]`, `north = tile[(py-1)*256+px]`, `south = tile[(py+1)*256+px]`, `east = tile[py*256+(px+1)]`, `west = tile[py*256+(px-1)]`.
6. `spacing = metersPerPixel(lat, z)`; `{slope, aspect} = pixelSlopeAspect(center, north, east, south, west, spacing)`.
7. Return `{ slope_deg: round(slope,1), aspect_deg: round(aspect,1), aspect_compass: aspectCompass(aspect), slope_bucket: slopeBucketLabel(slope) }`.

The function catches its own errors and returns `null` (never throws into `inspectPoint`).

## 8. Slope/aspect section shape

`App` wraps the sample into the existing `PointSection` type so `PointDashboard` renders it with no component changes:

- **ok:** `{ layer_id: "slope_aspect", title: "Slope & aspect", status: "ok", data: <SlopeAspectSample>, message: null, source: { name: <DEM attribution>, url: null, timestamp: <ISO now> } }`
- **empty:** `{ layer_id: "slope_aspect", title: "Slope & aspect", status: "empty", data: null, message: "No terrain data at this point", source: null }`

`PointDashboard.SlopeAspectValue` already renders `slope_deg`, `aspect_compass`, `slope_bucket`; `HazardValue`'s freeze/thaw branch already reads `aspect_compass` from the `slope_aspect` section — both keep working because the section is present in `result.sections`.

## 9. Error / empty handling

- DEM tile fetch fails, decode fails, or no DEM coverage (e.g. open ocean) → `sampleSlopeAspect` returns `null` → the card shows the calm `empty` state ("No terrain data at this point"). No error chip, no network error, no `429` — ever.
- The DEM source is the same one already used for shading/hover, so failures are rare and identical to what the hover readout already tolerates.

## 10. Testing

Vitest (frontend) + pytest (backend), tsc/build gate.

- **`terrainMath.test.ts`** — add cases for `aspectCompass` (cardinals + diagonals + wrap at 360) and `slopeBucketLabel` (each band boundary, e.g. 14.9→`0–15°`, 15→`15–25°`, 45→`45°+`).
- **`pointSample.test.ts`** (new) — feed a synthetic decoded tile into the cache (or mock `ensureTile`) representing a known planar gradient; assert `sampleSlopeAspect` returns the expected slope/aspect/compass/bucket. Test the lng/lat→tile/pixel conversion and the `[1,254]` edge clamp. Test that a failed tile load yields `null`.
- **Backend** — after removing the provider and its test, the suite must stay green (point-context returns the remaining sections; nothing imports `slope_aspect`).
- Manual: click around remote terrain rapidly — the card fills from the DEM with no `429`; click open water — calm "No terrain data".

## 11. Out of scope / future

- Elevation-card move to the DEM (keep USGS — authoritative).
- Progressive render (show other cards before the DEM tile resolves) — unnecessary given the concurrent fetch; can revisit if first-click latency is noticeable on cold tiles.
- An Open-Meteo fallback for slope/aspect — deliberately omitted; it is the exact path that rate-limits.
