# Gap-Filling Route Snapping with Non-OSM Trail Data — Design

Date: 2026-06-23
Status: Approved (design)

## Problem

The route builder snaps via OpenRouteService (ORS), which routes on OpenStreetMap
(OSM). Two failures occur together:

1. **All-or-nothing:** all waypoints are sent to ORS in one request. One
   un-routable waypoint 404s the *entire* route (ORS code 2010: "Could not find
   routable point within a radius of 350m of specified coordinate"). The user
   gets nothing snapped.
2. **Coverage gap:** the specific trail (visible in satellite) is not in OSM, so
   ORS cannot route through that point. Other OSM-based engines (GraphHopper,
   OSRM, Valhalla) share the same data and would not help.

## Goal

Snap routes wherever *any* source has data, and fall back gracefully. Fill OSM
gaps using a non-OSM trail-geometry dataset (USGS National Map / USFS trails),
and only draw honest straight-line bridges where no source has data.

This remains a **planning aid**, not a safety tool. Straight bridges and
trail-data legs are clearly labeled; the disclaimer posture is preserved.

## Constraints / decisions

- Public ArcGIS REST trail FeatureServers — **no API key** required.
- No new pip dependencies (hand-rolled Dijkstra + geometry helpers; matches the
  stdlib-leaning `gpx_parser`).
- Local-bbox trace only (not a national graph router).
- `points` stays a single concatenated polyline so save/render/bbox are unchanged.
- Saved routes store only the polyline (like GPX); no persisted per-segment data.
- Whole-route-first keeps the common case to one ORS call; per-segment only on
  failure. Waypoint count capped to bound work / rate limits.

## Existing code (relevant)

- `backend/app/services/routing_provider.py` — `snap_route(waypoints, profile,
  options)`; currently one ORS request, returns a `RouteSnapResponse` envelope;
  never raises. `_parse_ors_geojson` converts ORS `[lon,lat,ele_m]` → app
  `[lat,lon,ele_ft]`.
- `backend/app/services/route_builder.py` — `validate_points`,
  `haversine_length_miles`, `bbox_from_points`, `points_from_waypoints`.
- `backend/app/schemas.py` — `RouteSnapRequest`, `RouteSnapResponse`
  (status: success|failed|unavailable), `BuiltRouteSaveRequest`.
- `frontend/src/hooks/useRouteBuilder.ts` — `snappedPoints` non-null only when
  `snapped.status === "success"` and not stale.
- `frontend/src/components/MapView.tsx` — `route-builder-line` source with
  `route-builder-line-manual` (dashed) and `route-builder-line-snapped` (solid)
  layers.
- ORS tests mock `routing_provider.httpx.Client`.

## Architecture

### Layered orchestration (`routing_provider.snap_route`)

1. **Whole-route ORS** (fast path, current behavior). Success → return as today
   with `status="success"`.
2. On failure → **per-segment** over consecutive waypoint pairs. For each leg,
   fill via the first source that succeeds:
   a. **ORS leg** with widened `radiuses` (e.g. 1000 m), one retry at a larger
      radius (e.g. 5000 m) before giving up. provider tag `openrouteservice`.
   b. **Trail-data trace** (non-OSM). provider tag `trail_data`.
   c. **Straight-line bridge** (`[p1, p2]`). provider tag `bridge`.
3. Concatenate leg polylines (dropping duplicated shared endpoints). Compute
   combined length, bbox, elevation (from whatever legs carry elevation).
   `status` = `success` if every leg used ORS; `partial` if any leg used
   `trail_data` or `bridge`; `failed` only if ORS is reachable-but-broken in a
   way that yields no usable geometry and even bridging is impossible (e.g. <2
   waypoints — already handled).

### Non-OSM trail source (`backend/app/services/trail_source.py`)

- `fetch_trail_lines(bbox) -> list[list[[lat, lon], ...]]`: queries one or more
  ArcGIS REST trail FeatureServers by envelope and returns trail polylines.
- Sources configurable via env `SUMMIT_SIGNAL_TRAILS_URL` (comma-separated full
  `.../query` URLs). Default: a national trail dataset (USGS National Map
  trails); USFS NFS trails as an alternate. **The implementation plan must
  verify the default URL returns trails for the Mt. Rainier bbox**
  (lon −121.76, lat 46.85) and choose the best-coverage default, since national
  park trails may be absent from USFS-only data.
- ArcGIS query params: `geometry` (envelope), `geometryType=esriGeometryEnvelope`,
  `inSR=4326`, `outSR=4326`, `spatialRel=esriSpatialRelIntersects`,
  `returnGeometry=true`, `outFields=*`, `f=geojson`. Uses the shared httpx
  conventions. Never raises — returns `[]` on any error.

### Trail-network trace (`backend/app/services/trail_snap.py`, pure/offline)

- `snap_leg(p1, p2, trail_lines, *, snap_radius_m, merge_tol_m) -> list[[lat,lon,None]] | None`:
  1. Build an undirected graph: nodes = trail vertices; edges = consecutive
     vertices within each line, weight = haversine miles. Merge nodes within
     `merge_tol_m` (e.g. 15 m) so distinct features connect at shared endpoints.
  2. Snap `p1`/`p2` to nearest node within `snap_radius_m` (e.g. 200 m). If
     either fails to snap → return `None`.
  3. Hand-rolled Dijkstra between the two snapped nodes. Path found → return the
     polyline `[[lat, lon, None], ...]` (endpoints prepended/appended as the
     exact clicked points). No path → `None`.
- Helpers: `haversine_miles` (reuse from gpx_parser), `_node_key` (rounded
  coord), small binary-heap Dijkstra. No third-party deps.

## Response shape (`schemas.py`)

- `RouteSnapResponse.status` gains `"partial"`.
- Add `segments: list` of `{from: int, to: int, provider: str, length_miles:
  float|null, snapped: bool}` (`snapped` = not a bridge).
- `metadata` gains `providers_used: list[str]`, `bridged_segments: int`,
  `trail_segments: int`.
- `geojson` becomes a FeatureCollection of per-segment LineStrings tagged
  `properties.mode` = `"snapped"` | `"bridge"` (for distinct map styling). The
  full-route `points` array is still returned for save/preview/bbox.

## Frontend

- `types.ts`: add `"partial"` to the status union; add `segments` and the new
  metadata fields (loosely typed).
- `useRouteBuilder.ts`: treat `partial` like `success` for `snappedPoints`
  (it has geometry). Compose an honest message, e.g.: *"Snapped via OSM + trail
  data. N segment(s) had no trail data and are shown as straight lines — verify
  before relying on them."* Saving a `partial` route uses `source:
  "openrouteservice"` (snapped geometry) — unchanged save path.
- `MapView.tsx`: add a `route-builder-line-bridge` line layer (dashed red,
  filter `mode == "bridge"`) fed from the snapped geojson’s per-segment features,
  so bridged gaps are visually distinct from real snapped trail. Existing manual
  and snapped layers unchanged.
- `RouteBuilder.tsx`: stats/panel show providers used and bridged-segment count.

## Error handling

- Trail source unreachable / empty → that leg falls through to a bridge; overall
  still returns `partial`. Never raises.
- ORS unavailable (no key) → unchanged `unavailable` response (manual save still
  works); trail-data trace is only a *fallback within snapping*, not a snapping
  mode of its own for MVP.
- All failures surfaced in the message and via per-segment `provider` tags — no
  silent gaps.

## Testing (`backend/tests/test_trail_gap_fill.py` + additions)

- `trail_snap`: graph build, node merge across features, nearest-node snap,
  Dijkstra trace on synthetic lines; returns `None` when endpoints don't snap or
  no path exists.
- `trail_source`: mocked httpx → parses ArcGIS geojson into polylines; `[]` on
  error/non-200.
- Orchestration in `snap_route` (mock `httpx`): ORS whole-route fails → per-leg;
  one leg snapped by trail_data, one bridged → assert `status=="partial"`,
  `providers_used` includes `openrouteservice`/`trail_data`/`bridge` as
  appropriate, continuous `points`, `segments` tags correct, geojson per-segment
  `mode` set.
- Straight-bridge fallback when trail_source returns nothing.
- Existing ORS snap tests still pass (whole-route success path unchanged).
- Frontend: `npm run build` + `vitest`.

## Out of scope (later)

National/persistent trail graph; per-segment metadata persisted on the saved
route; elevation sampling for trail-data/bridge legs; additional providers;
caching trail tiles.
