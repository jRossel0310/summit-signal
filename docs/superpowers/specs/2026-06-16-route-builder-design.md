# In-App Route Builder — Design

Date: 2026-06-16
Status: Approved (design)

## Goal

Let users build a hiking/backpacking/mountaineering route directly on the map,
snap it to established trails where possible, preview stats, save it to a trip,
and have the rest of SummitSignal treat the saved route exactly like an uploaded
GPX route (map display + condition-check bbox).

This is a **planning aid**, not a safety decision tool. All UI copy preserves the
existing disclaimer posture: routes are based on available map/routing data and
are not guaranteed safe, legal, open, or passable.

## Constraints / decisions

- **UI placement:** map-overlay panel toggled by a "Build route" button (near
  `LayersControl`). Route building is map-centric and must coexist with live
  click-to-add-waypoint.
- **No schema change:** reuse the existing generic `GpxRoute` table. `name` is
  stored in `GpxRoute.filename`; `source`/provider `metadata` are **not**
  persisted for MVP (known at build time, shown in the panel). No DB reset for
  existing devs.
- **GPX export deferred** to a post-MVP nice-to-have.
- **Snapping is never mandatory.** Manual straight-line routes are always
  saveable and clearly labeled "manual / unsnapped".
- Do not remove or regress existing layers, GPX upload, terrain/fire layers,
  the point dashboard, or condition checks.

## Existing architecture (relevant facts)

- `GpxRoute` (models.py): generic table — `trip_id`, `filename`,
  `points_json` (`[[lat,lon,ele?],...]`), `bbox_json` (`{west,south,east,north}`),
  `length_miles`, `min_elevation_ft`, `max_elevation_ft`.
- `trips.py::upload_gpx` parses → creates `GpxRoute` → sets `trip.gpx_route_id`
  → returns `TripOut` via `_trip_out`. We mirror this for built routes.
- `_owned_trip(trip_id, user, db)` enforces ownership (404 otherwise).
- Condition checks consume the route **bbox** through the attached `GpxRoute`.
- Providers (e.g. `aqi.py`) follow a `requires_key` pattern; API keys come from
  env vars only, surfaced via `settings_service.ENV_KEY_MAP` / `api_keys_present`.
- Connectors share an `httpx` client in `connectors/base.py` (`USER_AGENT`,
  `DEFAULT_TIMEOUT`, `follow_redirects`).
- Frontend point convention is `[lat, lon, ele]`; GeoJSON is `[lon, lat]`.
- `MapView` already has a `gpx` source/layer and a click handler that branches on
  the `trips-circle` layer. App owns `selectedPoint`, `selectedTrip`, `gpxPoints`.

## Backend

### `services/routing_provider.py`
Provider abstraction + first provider.

- `snap_route(waypoints, profile, options) -> dict` → the `RouteSnapResponse` shape.
- `OpenRouteServiceProvider`: reads `SUMMIT_SIGNAL_ORS_KEY`. POSTs to
  `https://api.openrouteservice.org/v2/directions/{ors_profile}/geojson` with
  `coordinates` (`[lon,lat]`), `elevation: true`,
  `extra_info: [steepness, surface, waytype, traildifficulty, osmid]`. Uses the
  existing httpx conventions.
- Profile map: `hiking → foot-hiking` (default), `walking → foot-walking`.
- No key → `{status:"unavailable", message, provider:"none", ...}`.
  HTTP/parse error → `{status:"failed", message, ...}`. Never raises.
- Converts ORS `[lon,lat,ele_m]` → points `[lat,lon,ele_ft]`; distance m → miles;
  passes through `bbox` `[minLon,minLat,maxLon,maxLat]`, raw `geojson`, and a
  `metadata` dict (provider, profile, extras present).
- Add `"ors": "SUMMIT_SIGNAL_ORS_KEY"` to `settings_service.ENV_KEY_MAP`.

### `services/route_builder.py`
Pure geometry (no network):
- `validate_waypoints(waypoints)` — ≥2, each in lat/lon range (raises ValueError).
- `haversine_length_miles(points)` — reuse `gpx_parser._haversine_miles`.
- `bbox_from_points(points)` — returns both `[minLon,minLat,maxLon,maxLat]` and
  storage form `{west,south,east,north}`.
- `points_from_waypoints(waypoints)` — straight-line `[lat,lon,None]` points.

### `routes/routes.py` (new router, registered in `main.py`)
- `POST /routes/snap` (auth) → `routing_provider.snap_route`. Returns `200` with
  `status` even when unavailable/failed (UI distinguishes no-key vs network error).
- `POST /trips/{trip_id}/built-route` (auth, `_owned_trip`) → build `GpxRoute`
  from posted points, set `trip.gpx_route_id`, return `TripOut` (mirrors
  `upload_gpx`). `name` → `filename`. Invalid points → `400`.

### `schemas.py`
Add `RouteWaypoint`, `RouteSnapRequest`, `RouteSnapResponse`, `BuiltRouteSaveRequest`.
No model changes.

## Frontend

- `types.ts`: `RouteWaypoint`, `RouteSnapRequest`, `RouteSnapResponse`,
  `BuiltRouteSaveRequest`.
- `lib/api.ts`: `snapRoute(req)`, `saveBuiltRoute(tripId, req)`.
- `hooks/useRouteBuilder.ts`: owns all route-building state — `mode`,
  `waypoints`, `snapped` result, `stale` flag, status `message`. Editing a
  waypoint after a snap sets `stale = true`. Keeps MapView/App clean.
- `components/RouteBuilder.tsx`: map-overlay panel. Controls — enter/exit mode,
  undo last, clear, Snap to trails, Save to trip; live stats (distance,
  #waypoints, provider/profile, snapped-vs-manual); unavailable/manual warning;
  verbatim safety copy (requirement H). Save disabled with a hint when no trip
  selected.
- `MapView.tsx`: new props `routeMode`, `routeWaypoints`, `routeSnappedPoints`,
  `onRouteAddWaypoint`, `onRouteMoveWaypoint`. Isolated sources/layers
  `route-builder-line` (manual = dashed, snapped = solid/prominent),
  `route-builder-waypoints`, `route-builder-labels` (numbered). In route mode:
  empty-map click adds a waypoint, trip-marker click still selects a trip,
  cursor → crosshair. Draggable waypoint markers. Existing layers untouched.
- `App.tsx`: instantiate `useRouteBuilder`, render `RouteBuilder` in
  `panel-center`, wire slices into `MapView`, pass selected trip id; on save,
  refresh trips so the route renders via the existing `gpxPoints` path.

## Data flow (happy path)

Select/create trip → toggle Build route → click map to add waypoints (draft
dashed line at ≥2) → Snap to trails → solid ORS line + stats → Save →
`POST /trips/{id}/built-route` → `TripOut` → App refreshes → route shows via the
existing `gpx` layer and condition checks use its bbox.

## Error handling

- No key → "Trail snapping unavailable (no routing provider configured) — you can
  still save this as a manual, unsnapped route."
- Snap failure → visible error; draft route preserved.
- Edit after snap → "Snapped route is stale — re-snap to update."
- Save with no trip → disabled + hint.

## Tests

`backend/tests/test_route_builder.py`:
- snap returns `unavailable` when `SUMMIT_SIGNAL_ORS_KEY` unset.
- save built route creates a GpxRoute + attaches it to an owned trip.
- cannot save to another user's trip → 404.
- bbox/length helpers on a normal point array.
- invalid points (<2 / out of range) → 400.
- ORS provider success path with a mocked httpx response (no live network).

Frontend: `npm run build` (type check) + existing tests.

## Docs

`.env.example` + README gain `SUMMIT_SIGNAL_ORS_KEY` with a note that snapping
requires a configured routing provider and is a planning aid only.

## Out of scope (post-MVP)

GPX export, route reversal, mid-route waypoint insertion, per-segment distances,
provider surface/steepness summaries, alternate providers (Valhalla/GraphHopper),
DEM elevation sampling for manual routes.
