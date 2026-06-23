# Trail Gap-Fill Snapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make route snapping resilient — snap each leg with the best available source (ORS → non-OSM trail data → straight bridge) instead of failing the whole route when one waypoint isn't in OpenStreetMap.

**Architecture:** A pure trail-network tracer (`trail_snap`) and an ArcGIS trail-geometry fetcher (`trail_source`) become per-leg fallbacks inside a rewritten `routing_provider.snap_route`: it tries the whole route via ORS first, and on failure snaps leg-by-leg, filling unroutable legs from non-OSM trail data and only bridging with straight lines as a last resort. The response gains a `partial` status, per-segment provider tags, and a per-segment GeoJSON so the frontend can render bridges distinctly.

**Tech Stack:** FastAPI, SQLAlchemy, httpx, pytest (backend); Vite + React + TypeScript + MapLibre GL, vitest (frontend). No new pip/npm dependencies.

## Global Constraints

- No new pip or npm dependencies (hand-rolled Dijkstra + geometry; matches stdlib-leaning `gpx_parser`).
- Backend services never raise to the caller — failures/empties return a status envelope or `[]`/`None`.
- Point convention is `[lat, lon, ele_ft|None]`; GeoJSON coordinates are `[lon, lat]`.
- Trail sources are public ArcGIS REST FeatureServers — no API key. Configurable via env `SUMMIT_SIGNAL_TRAILS_URL` (comma-separated `.../query` URLs).
- `RouteSnapResponse.points` stays a single concatenated polyline so the save/render/bbox paths are unchanged.
- Existing snap tests in `backend/tests/test_route_builder.py` must keep passing (whole-route ORS success path is preserved).
- Waypoints capped at 50 per snap request.

---

## Task 1: Trail-network tracer (`trail_snap.py`)

**Files:**
- Create: `backend/app/services/trail_snap.py`
- Test: `backend/tests/test_trail_gap_fill.py`

**Interfaces:**
- Consumes: `_haversine_miles(lat1, lon1, lat2, lon2)` from `app.services.gpx_parser`.
- Produces: `snap_leg(p1, p2, trail_lines, snap_radius_m=200.0, merge_tol_m=15.0) -> list[[lat,lon,None]] | None` where `p1`/`p2` are `(lat, lon)` tuples and `trail_lines` is `list[list[[lat, lon]]]`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_trail_gap_fill.py`:

```python
"""Trail gap-fill: offline tracer, ArcGIS trail fetch (mocked), and per-segment
snap orchestration. No live network."""
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "trailgap.db"))

import pytest  # noqa: E402
from app.services import trail_snap  # noqa: E402


# A trail running roughly west->east along latitude 46.10, every ~0.01 deg lon.
STRAIGHT_TRAIL = [[[46.10, -121.10], [46.10, -121.09], [46.10, -121.08],
                   [46.10, -121.07], [46.10, -121.06], [46.10, -121.05]]]


def test_snap_leg_traces_along_single_trail():
    p1 = (46.1001, -121.0995)   # ~near the west end
    p2 = (46.0998, -121.0505)   # ~near the east end
    traced = trail_snap.snap_leg(p1, p2, STRAIGHT_TRAIL)
    assert traced is not None
    assert traced[0] == [p1[0], p1[1], None]
    assert traced[-1] == [p2[0], p2[1], None]
    assert len(traced) >= 4          # endpoints + interior trail vertices
    assert all(len(pt) == 3 and pt[2] is None for pt in traced)


def test_snap_leg_connects_two_trails_sharing_an_endpoint():
    # Two segments meeting at [46.10, -121.05] (within merge tolerance).
    line_a = [[46.10, -121.10], [46.10, -121.05]]
    line_b = [[46.10, -121.05], [46.10, -121.00]]
    traced = trail_snap.snap_leg((46.10, -121.099), (46.10, -121.001), [line_a, line_b])
    assert traced is not None
    assert traced[-1] == [46.10, -121.001, None]


def test_snap_leg_returns_none_when_endpoint_too_far():
    # p1 is ~1.5 km north of the trail -> beyond the 200 m snap radius.
    traced = trail_snap.snap_leg((46.115, -121.10), (46.10, -121.05), STRAIGHT_TRAIL)
    assert traced is None


def test_snap_leg_returns_none_when_no_path():
    far_trail = [[[40.0, -100.0], [40.0, -100.01]]]   # nowhere near the points
    traced = trail_snap.snap_leg((46.10, -121.10), (46.10, -121.05), far_trail)
    assert traced is None


def test_snap_leg_returns_none_on_empty():
    assert trail_snap.snap_leg((46.10, -121.10), (46.10, -121.05), []) is None
```

- [ ] **Step 2: Run the tracer tests to verify they fail**

Run: `cd c:\Users\jacob\summit-signal/backend && python -m pytest tests/test_trail_gap_fill.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.trail_snap'`.

- [ ] **Step 3: Implement `trail_snap.py`**

Create `backend/app/services/trail_snap.py`:

```python
"""Offline trail-network tracing for gap-filling route snapping. Given a leg's
two endpoints and nearby trail polylines (from trail_source), build a small local
graph and trace the shortest path along the trails between the endpoints.

Pure: no network, no DB. Never raises — returns None when it can't trace."""
from __future__ import annotations
import heapq

from .gpx_parser import _haversine_miles

_M_PER_DEG = 111_000.0  # ~meters per degree latitude (good enough locally)


def _node_key(lat: float, lon: float, step_deg: float) -> tuple:
    return (round(lat / step_deg), round(lon / step_deg))


def _dist_m(lat1, lon1, lat2, lon2) -> float:
    return _haversine_miles(lat1, lon1, lat2, lon2) * 1609.344


def snap_leg(p1, p2, trail_lines, snap_radius_m: float = 200.0,
             merge_tol_m: float = 15.0):
    """p1, p2: (lat, lon). trail_lines: list of polylines [[lat, lon], ...].
    Returns [[lat, lon, None], ...] from p1 to p2 traced along trails, or None."""
    if not trail_lines:
        return None
    step = max(merge_tol_m, 1.0) / _M_PER_DEG
    coords: dict = {}   # key -> (lat, lon) representative
    adj: dict = {}      # key -> {neighbor_key: weight_miles}

    def add_node(lat, lon):
        k = _node_key(lat, lon, step)
        if k not in coords:
            coords[k] = (lat, lon)
            adj[k] = {}
        return k

    def add_edge(a, b):
        (la, lo) = coords[a]
        (lb, lob) = coords[b]
        w = _haversine_miles(la, lo, lb, lob)
        if b not in adj[a] or w < adj[a][b]:
            adj[a][b] = w
            adj[b][a] = w

    for line in trail_lines:
        prev = None
        for pt in line:
            if pt is None or len(pt) < 2 or pt[0] is None or pt[1] is None:
                continue
            k = add_node(pt[0], pt[1])
            if prev is not None and prev != k:
                add_edge(prev, k)
            prev = k

    if not coords:
        return None

    def nearest(lat, lon):
        best_k, best_d = None, None
        for k, (clat, clon) in coords.items():
            d = _dist_m(lat, lon, clat, clon)
            if best_d is None or d < best_d:
                best_k, best_d = k, d
        return best_k, best_d

    s_key, s_d = nearest(p1[0], p1[1])
    g_key, g_d = nearest(p2[0], p2[1])
    if s_key is None or g_key is None or s_d > snap_radius_m or g_d > snap_radius_m:
        return None

    path = _dijkstra(adj, s_key, g_key)
    if path is None:
        return None

    out = [[p1[0], p1[1], None]]
    for k in path:
        lat, lon = coords[k]
        if out[-1][0] != lat or out[-1][1] != lon:
            out.append([lat, lon, None])
    if out[-1][0] != p2[0] or out[-1][1] != p2[1]:
        out.append([p2[0], p2[1], None])
    return out


def _dijkstra(adj, start, goal):
    if start == goal:
        return [start]
    dist = {start: 0.0}
    prev: dict = {}
    pq = [(0.0, start)]
    visited = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == goal:
            break
        for v, w in adj.get(u, {}).items():
            nd = d + w
            if v not in dist or nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    if goal not in dist:
        return None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path
```

- [ ] **Step 4: Run the tracer tests to verify they pass**

Run: `cd c:\Users\jacob\summit-signal/backend && python -m pytest tests/test_trail_gap_fill.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/trail_snap.py backend/tests/test_trail_gap_fill.py
git commit -m "feat(trail-gap-fill): offline trail-network tracer + tests"
```

---

## Task 2: ArcGIS trail source (`trail_source.py`) + default URL + docs

**Files:**
- Create: `backend/app/services/trail_source.py`
- Modify: `.env.example`, `README.md`
- Test: append to `backend/tests/test_trail_gap_fill.py`

**Interfaces:**
- Produces: `fetch_trail_lines(bbox, urls=None) -> list[list[[lat, lon]]]` where `bbox` is `(min_lon, min_lat, max_lon, max_lat)`. Returns `[]` on any error. Also exposes module constant `DEFAULT_TRAILS_URLS: list[str]`.

- [ ] **Step 1: Verify a working public trail endpoint for the failing area**

The reported failure is near Mt. Rainier (lon −121.7576, lat 46.8526). Confirm the default USFS endpoint returns trail features there:

Run:
```bash
curl -s "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSTrails_01/MapServer/0/query?geometry=-121.80,46.83,-121.72,46.88&geometryType=esriGeometryEnvelope&inSR=4326&outSR=4326&spatialRel=esriSpatialRelIntersects&returnGeometry=true&outFields=*&resultRecordCount=5&f=geojson" | head -c 400
```
Expected: a GeoJSON `FeatureCollection`. Note whether `features` is non-empty.

- If it returns features → keep `DEFAULT_TRAILS_URLS = [<that USFS url>]`.
- If `features` is empty (Mt. Rainier NP is not National Forest), find the USGS National Map trail layer: open `https://carto.nationalmap.gov/arcgis/rest/services/transportation/MapServer?f=json`, locate the layer whose name contains "Trail", and use `https://carto.nationalmap.gov/arcgis/rest/services/transportation/MapServer/<id>/query`. Verify it with the same query params/bbox. Put the working URL(s) first in `DEFAULT_TRAILS_URLS` (you may keep both USGS and USFS in the list).

Record in your report which URL(s) you verified and the feature counts.

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/test_trail_gap_fill.py`:

```python
from app.services import trail_source  # noqa: E402


def _fake_get_client(payload, status=200):
    class FakeResp:
        status_code = status
        def json(self):
            return payload
    class FakeClient:
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get(self, *a, **k):
            return FakeResp()
    return FakeClient


def test_fetch_trail_lines_parses_linestring_and_multiline(monkeypatch):
    payload = {"type": "FeatureCollection", "features": [
        {"geometry": {"type": "LineString",
                      "coordinates": [[-121.10, 46.10], [-121.09, 46.10]]}},
        {"geometry": {"type": "MultiLineString",
                      "coordinates": [[[-121.08, 46.10], [-121.07, 46.10]],
                                      [[-121.06, 46.11], [-121.05, 46.11]]]}},
    ]}
    monkeypatch.setattr(trail_source.httpx, "Client", _fake_get_client(payload))
    lines = trail_source.fetch_trail_lines((-121.2, 46.0, -121.0, 46.2),
                                           urls=["http://example/query"])
    assert len(lines) == 3
    # [lon, lat] in source -> [lat, lon] out
    assert lines[0][0] == [46.10, -121.10]


def test_fetch_trail_lines_empty_on_non_200(monkeypatch):
    monkeypatch.setattr(trail_source.httpx, "Client", _fake_get_client({}, status=500))
    assert trail_source.fetch_trail_lines((-121.2, 46.0, -121.0, 46.2),
                                          urls=["http://example/query"]) == []


def test_fetch_trail_lines_empty_on_exception(monkeypatch):
    class Boom:
        def __init__(self, *a, **k):
            pass
        def __enter__(self):
            raise RuntimeError("network down")
        def __exit__(self, *a):
            return False
    monkeypatch.setattr(trail_source.httpx, "Client", Boom)
    assert trail_source.fetch_trail_lines((-121.2, 46.0, -121.0, 46.2),
                                          urls=["http://example/query"]) == []
```

- [ ] **Step 3: Run the source tests to verify they fail**

Run: `cd c:\Users\jacob\summit-signal/backend && python -m pytest tests/test_trail_gap_fill.py -k "fetch_trail" -q`
Expected: FAIL — `No module named 'app.services.trail_source'`.

- [ ] **Step 4: Implement `trail_source.py`**

Create `backend/app/services/trail_source.py` (set `DEFAULT_TRAILS_URLS` to the URL(s) verified in Step 1):

```python
"""Fetch non-OSM trail geometry from public ArcGIS REST FeatureServers (USGS
National Map / USFS trails) by bbox. No API key. Never raises — returns [] on
any error. Used to fill OSM gaps in route snapping."""
from __future__ import annotations
import os

import httpx

USER_AGENT = "SummitSignal/0.2 (trip-planning tool; trail snap)"
TIMEOUT = 20.0
MAX_FEATURES = 600

# Verified against the Mt. Rainier bbox during implementation. Override with
# SUMMIT_SIGNAL_TRAILS_URL (comma-separated .../query URLs).
DEFAULT_TRAILS_URLS = [
    "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSTrails_01/MapServer/0/query",
]


def _urls() -> list:
    raw = os.environ.get("SUMMIT_SIGNAL_TRAILS_URL", "").strip()
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    return DEFAULT_TRAILS_URLS


def fetch_trail_lines(bbox, urls=None) -> list:
    """bbox: (min_lon, min_lat, max_lon, max_lat). Returns list of polylines
    [[lat, lon], ...]. [] on any error/empty."""
    out: list = []
    for url in (urls if urls is not None else _urls()):
        try:
            out.extend(_fetch_one(url, bbox))
        except Exception:  # noqa: BLE001
            continue
        if len(out) >= MAX_FEATURES:
            break
    return out


def _fetch_one(url, bbox) -> list:
    min_lon, min_lat, max_lon, max_lat = bbox
    params = {
        "geometry": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326", "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "true", "outFields": "*",
        "resultRecordCount": str(MAX_FEATURES),
        "f": "geojson",
    }
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as cli:
        resp = cli.get(url, params=params)
    if resp.status_code != 200:
        return []
    return _parse_geojson(resp.json())


def _parse_geojson(data) -> list:
    lines = []
    for feat in (data or {}).get("features") or []:
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        if gtype == "LineString":
            lines.append([[c[1], c[0]] for c in coords if len(c) >= 2])
        elif gtype == "MultiLineString":
            for part in coords:
                lines.append([[c[1], c[0]] for c in part if len(c) >= 2])
    return [ln for ln in lines if len(ln) >= 2]
```

- [ ] **Step 5: Run the source tests to verify they pass**

Run: `cd c:\Users\jacob\summit-signal/backend && python -m pytest tests/test_trail_gap_fill.py -k "fetch_trail" -q`
Expected: 3 passed.

- [ ] **Step 6: Document the env var**

In `.env.example`, after the `SUMMIT_SIGNAL_ORS_KEY=` block, add:

```
# Optional: comma-separated ArcGIS REST trail query URLs used to fill gaps where
# OpenStreetMap lacks a trail. No API key needed. Defaults to a public USFS/USGS
# trail service. Routes remain planning aids only.
SUMMIT_SIGNAL_TRAILS_URL=
```

In `README.md`, add a row to the env table (match the existing 2-column format):

```
| `SUMMIT_SIGNAL_TRAILS_URL` | Optional comma-separated ArcGIS REST trail query URLs (no key) to fill OSM gaps in route snapping. Defaults to a public trail service. |
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/trail_source.py backend/tests/test_trail_gap_fill.py .env.example README.md
git commit -m "feat(trail-gap-fill): ArcGIS trail source + env docs"
```

---

## Task 3: Per-segment snap orchestration (`routing_provider.py`) + schema

**Files:**
- Modify: `backend/app/schemas.py` (add `segments` to `RouteSnapResponse`)
- Modify: `backend/app/services/routing_provider.py` (rewrite orchestration)
- Test: append to `backend/tests/test_trail_gap_fill.py`

**Interfaces:**
- Consumes: `trail_source.fetch_trail_lines(bbox)`, `trail_snap.snap_leg(p1, p2, lines)`, `route_builder.haversine_length_miles(points)`, `route_builder.bbox_from_points(points)["array"]`, `settings_service.get_api_key(None, "ors")`.
- Produces (unchanged public entry): `snap_route(waypoints, profile="hiking", options=None) -> dict` with envelope keys `status, message, provider, profile, points, geojson, length_miles, bbox, metadata, segments`. `status` ∈ `success | partial | failed | unavailable`. `segments` = list of `{from, to, provider, snapped, length_miles}`. `geojson` = per-segment `FeatureCollection` with `properties.mode` ∈ `snapped|bridge`.

- [ ] **Step 1: Add `segments` to the response schema**

In `backend/app/schemas.py`, in class `RouteSnapResponse`, add this field (after `metadata`):

```python
    segments: list = Field(default_factory=list)      # [{from,to,provider,snapped,length_miles}]
```

- [ ] **Step 2: Write the orchestration tests**

Append to `backend/tests/test_trail_gap_fill.py`:

```python
from app.services import routing_provider as rp  # noqa: E402


def test_snap_route_partial_mixes_ors_trail_and_bridge(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_ORS_KEY", "test-key")
    # Force the whole-route fast path to fail so we go per-segment.
    monkeypatch.setattr(rp, "_ors_whole", lambda wps, prof, key: None)
    # 3 waypoints => 2 legs. Leg 0 snaps via ORS; leg 1 fails ORS.
    def fake_ors_leg(p1, p2, prof, key):
        if (p1, p2) == ((46.0, -121.0), (46.1, -121.1)):
            return {"points": [[46.0, -121.0, 100.0], [46.1, -121.1, 200.0]],
                    "length_miles": 1.0}
        return None
    monkeypatch.setattr(rp, "_ors_leg", fake_ors_leg)
    # Leg 1: trail data provides a trace.
    monkeypatch.setattr(rp.trail_source, "fetch_trail_lines",
                        lambda bbox: [[[46.1, -121.1], [46.2, -121.2]]])
    monkeypatch.setattr(rp.trail_snap, "snap_leg",
                        lambda p1, p2, lines: [[46.1, -121.1, None],
                                               [46.15, -121.15, None],
                                               [46.2, -121.2, None]])
    res = rp.snap_route([(46.0, -121.0), (46.1, -121.1), (46.2, -121.2)], "hiking")
    assert res["status"] == "partial"
    assert res["provider"] == "mixed"
    assert [s["provider"] for s in res["segments"]] == ["openrouteservice", "trail_data"]
    assert res["metadata"]["trail_segments"] == 1
    assert res["metadata"]["bridged_segments"] == 0
    # points are continuous (shared waypoint not duplicated)
    assert res["points"][0] == [46.0, -121.0, 100.0]
    assert res["points"][-1] == [46.2, -121.2, None]
    modes = [f["properties"]["mode"] for f in res["geojson"]["features"]]
    assert modes == ["snapped", "snapped"]


def test_snap_route_bridges_when_no_source(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_ORS_KEY", "test-key")
    monkeypatch.setattr(rp, "_ors_whole", lambda wps, prof, key: None)
    monkeypatch.setattr(rp, "_ors_leg", lambda p1, p2, prof, key: None)
    monkeypatch.setattr(rp.trail_source, "fetch_trail_lines", lambda bbox: [])
    res = rp.snap_route([(46.0, -121.0), (46.1, -121.1)], "hiking")
    assert res["status"] == "partial"
    assert res["segments"][0]["provider"] == "bridge"
    assert res["metadata"]["bridged_segments"] == 1
    assert res["geojson"]["features"][0]["properties"]["mode"] == "bridge"
    assert res["points"] == [[46.0, -121.0, None], [46.1, -121.1, None]]


def test_snap_route_rejects_too_many_waypoints(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_ORS_KEY", "test-key")
    wps = [(46.0 + i * 0.001, -121.0) for i in range(51)]
    res = rp.snap_route(wps, "hiking")
    assert res["status"] == "failed"
```

- [ ] **Step 3: Run the orchestration tests to verify they fail**

Run: `cd c:\Users\jacob\summit-signal/backend && python -m pytest tests/test_trail_gap_fill.py -k "snap_route" -q`
Expected: FAIL — `_ors_whole`/`_ors_leg` don't exist yet, or `status`/`segments` mismatch.

- [ ] **Step 4: Rewrite `routing_provider.py`**

Replace the entire contents of `backend/app/services/routing_provider.py` with:

```python
"""Route snapping. Fast path: one OpenRouteService (ORS) request for the whole
route. On failure, snap per-segment, filling each leg with the best available
source: ORS (widened radius) -> non-OSM trail data (trail_source + trail_snap)
-> an honest straight-line bridge. Reads keys/URLs from the environment only.
Never raises: failures come back as a status envelope the frontend can render."""
from __future__ import annotations

import httpx

from .settings_service import get_api_key
from . import route_builder, trail_source, trail_snap

ORS_BASE = "https://api.openrouteservice.org/v2/directions"
PROFILE_MAP = {"hiking": "foot-hiking", "walking": "foot-walking"}
DEFAULT_PROFILE = "hiking"
EXTRA_INFO = ["steepness", "surface", "waytype", "traildifficulty", "osmid"]
USER_AGENT = "SummitSignal/0.2 (trip-planning tool; route builder)"
TIMEOUT = 25.0
METERS_PER_MILE = 1609.344
FT_PER_METER = 3.28084
MAX_WAYPOINTS = 50
LEG_RADII_M = [1000, 5000]   # ORS per-leg snap radii to try in order
TRAIL_BBOX_PAD_DEG = 0.02    # ~2 km padding around a leg when fetching trails


def _envelope(status, provider, profile, message=None, points=None, geojson=None,
              length_miles=None, bbox=None, metadata=None, segments=None):
    return {
        "status": status, "message": message, "provider": provider, "profile": profile,
        "points": points or [], "geojson": geojson, "length_miles": length_miles,
        "bbox": bbox, "metadata": metadata or {}, "segments": segments or [],
    }


def snap_route(waypoints, profile: str = DEFAULT_PROFILE, options: dict | None = None) -> dict:
    """waypoints: [(lat, lon), ...]. Returns the RouteSnapResponse dict shape.
    Never raises."""
    profile = profile if profile in PROFILE_MAP else DEFAULT_PROFILE
    if not waypoints or len(waypoints) < 2:
        return _envelope("failed", "none", profile,
                         message="At least two waypoints are required to snap a route.")
    if len(waypoints) > MAX_WAYPOINTS:
        return _envelope("failed", "none", profile,
                         message=f"Too many waypoints to snap (max {MAX_WAYPOINTS}). "
                                 "Reduce the number of waypoints.")
    key = get_api_key(None, "ors")
    if not key:
        return _envelope("unavailable", "none", profile,
                         message="Trail snapping is not configured. Set SUMMIT_SIGNAL_ORS_KEY "
                                 "on the server to enable it.")
    ors_profile = PROFILE_MAP[profile]
    try:
        # Fast path: the whole route in one request.
        whole = _ors_whole(waypoints, ors_profile, key)
        if whole is not None:
            seg = [{"from": 0, "to": len(waypoints) - 1, "provider": "openrouteservice",
                    "snapped": True, "length_miles": whole["length_miles"]}]
            return _finish(whole["points"], profile, seg, [whole["points"]], ["snapped"])

        # Per-segment fallback.
        legs = [_snap_one_leg(waypoints[i], waypoints[i + 1], ors_profile, key)
                for i in range(len(waypoints) - 1)]
        points = _concat([leg["points"] for leg in legs])
        segments, leg_points, leg_modes = [], [], []
        for i, leg in enumerate(legs):
            segments.append({"from": i, "to": i + 1, "provider": leg["provider"],
                             "snapped": leg["snapped"], "length_miles": leg["length_miles"]})
            leg_points.append(leg["points"])
            leg_modes.append("snapped" if leg["snapped"] else "bridge")
        return _finish(points, profile, segments, leg_points, leg_modes)
    except Exception as e:  # noqa: BLE001
        return _envelope("failed", "openrouteservice", profile,
                         message=f"Route snapping failed: {e}")


def _finish(points, profile, segments, leg_points, leg_modes):
    length = round(sum((s.get("length_miles") or 0.0) for s in segments), 2)
    bbox = route_builder.bbox_from_points(points)["array"] if points else None
    features = []
    for pts, mode in zip(leg_points, leg_modes):
        if len(pts) < 2:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString",
                         "coordinates": [[p[1], p[0]] for p in pts]},
            "properties": {"mode": mode},
        })
    geojson = {"type": "FeatureCollection", "features": features}
    status = "success" if all(s["provider"] == "openrouteservice" for s in segments) else "partial"
    provider = "openrouteservice" if status == "success" else "mixed"
    metadata = {
        "providers_used": sorted({s["provider"] for s in segments}),
        "bridged_segments": sum(1 for s in segments if s["provider"] == "bridge"),
        "trail_segments": sum(1 for s in segments if s["provider"] == "trail_data"),
        "ors_profile": PROFILE_MAP[profile],
    }
    return _envelope(status, provider, profile, points=points, geojson=geojson,
                     length_miles=length, bbox=bbox, metadata=metadata, segments=segments)


def _snap_one_leg(p1, p2, ors_profile, key):
    res = _ors_leg(p1, p2, ors_profile, key)
    if res is not None:
        return {"points": res["points"], "provider": "openrouteservice",
                "snapped": True, "length_miles": res["length_miles"]}
    bbox = (min(p1[1], p2[1]) - TRAIL_BBOX_PAD_DEG, min(p1[0], p2[0]) - TRAIL_BBOX_PAD_DEG,
            max(p1[1], p2[1]) + TRAIL_BBOX_PAD_DEG, max(p1[0], p2[0]) + TRAIL_BBOX_PAD_DEG)
    lines = trail_source.fetch_trail_lines(bbox)
    traced = trail_snap.snap_leg(p1, p2, lines)
    if traced is not None and len(traced) >= 2:
        return {"points": traced, "provider": "trail_data", "snapped": True,
                "length_miles": route_builder.haversine_length_miles(traced)}
    pts = [[p1[0], p1[1], None], [p2[0], p2[1], None]]
    return {"points": pts, "provider": "bridge", "snapped": False,
            "length_miles": route_builder.haversine_length_miles(pts)}


def _ors_whole(waypoints, ors_profile, key):
    coords = [[lon, lat] for (lat, lon) in waypoints]
    return _ors_request(coords, ors_profile, key)


def _ors_leg(p1, p2, ors_profile, key):
    coords = [[p1[1], p1[0]], [p2[1], p2[0]]]
    for r in LEG_RADII_M:
        res = _ors_request(coords, ors_profile, key, radiuses=[r, r])
        if res is not None:
            return res
    return None


def _ors_request(coords, ors_profile, key, radiuses=None):
    body = {"coordinates": coords, "elevation": True, "extra_info": EXTRA_INFO}
    if radiuses is not None:
        body["radiuses"] = radiuses
    try:
        with httpx.Client(timeout=TIMEOUT, headers={
            "Authorization": key, "User-Agent": USER_AGENT,
            "Content-Type": "application/json", "Accept": "application/geo+json",
        }) as cli:
            resp = cli.post(f"{ORS_BASE}/{ors_profile}/geojson", json=body)
    except Exception:  # noqa: BLE001
        return None
    if resp.status_code != 200:
        return None
    return _extract_ors(resp.json())


def _extract_ors(data):
    features = (data or {}).get("features") or []
    if not features:
        return None
    feat = features[0]
    coords = (feat.get("geometry") or {}).get("coordinates") or []
    if len(coords) < 2:
        return None
    points = []
    for c in coords:
        ele_ft = round(c[2] * FT_PER_METER, 1) if len(c) > 2 and c[2] is not None else None
        points.append([c[1], c[0], ele_ft])
    summary = (feat.get("properties") or {}).get("summary") or {}
    dist_m = summary.get("distance")
    length_miles = (round(dist_m / METERS_PER_MILE, 2) if dist_m is not None
                    else route_builder.haversine_length_miles(points))
    return {"points": points, "length_miles": length_miles}


def _concat(leg_point_lists):
    out = []
    for pts in leg_point_lists:
        for p in pts:
            if out and out[-1][0] == p[0] and out[-1][1] == p[1]:
                continue
            out.append(p)
    return out
```

- [ ] **Step 5: Run the new orchestration tests**

Run: `cd c:\Users\jacob\summit-signal/backend && python -m pytest tests/test_trail_gap_fill.py -k "snap_route" -q`
Expected: 3 passed.

- [ ] **Step 6: Run the pre-existing route-builder snap tests (no regression)**

Run: `cd c:\Users\jacob\summit-signal/backend && python -m pytest tests/test_route_builder.py -q`
Expected: all pass (the whole-route ORS success path and `unavailable` path are unchanged; `test_snap_success_with_mocked_ors` still gets status `success`, 3 points, length ~5.0, bbox `[-121.1, 46.0, -121.0, 46.1]`).

- [ ] **Step 7: Run the whole backend suite**

Run: `cd c:\Users\jacob\summit-signal/backend && python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/services/routing_provider.py backend/tests/test_trail_gap_fill.py
git commit -m "feat(trail-gap-fill): per-segment snap orchestration with trail/bridge fallback"
```

---

## Task 4: Frontend types + hook (`partial` handling)

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/hooks/useRouteBuilder.ts`

**Interfaces:**
- Consumes: `RouteSnapResponse` (now with `status: "partial"`, `segments`, `geojson` FeatureCollection).
- Produces: `RouteBuilderState` gains `snappedGeojson: GeoJSON.FeatureCollection | GeoJSON.Feature | null`. `snappedPoints` is non-null for `success` OR `partial`.

- [ ] **Step 1: Update types**

In `frontend/src/types.ts`, change the `RouteSnapResponse` interface:
- In the `status` union add `"partial"`:
```typescript
  status: "success" | "partial" | "failed" | "unavailable";
```
- Add a `segments` field (place after `metadata`):
```typescript
  segments?: { from: number; to: number; provider: string; snapped: boolean; length_miles: number | null }[];
```

- [ ] **Step 2: Update the hook**

In `frontend/src/hooks/useRouteBuilder.ts`:

(a) Add `snappedGeojson` to the `RouteBuilderState` interface (after `snappedPoints`):
```typescript
  snappedGeojson: GeoJSON.FeatureCollection | GeoJSON.Feature | null;
```

(b) Change the `snappedPoints` memo to accept `partial`, and add a `snappedGeojson` memo right after it:
```typescript
  const snappedPoints = useMemo(
    () => (snapped && (snapped.status === "success" || snapped.status === "partial") && !stale
      ? snapped.points : null),
    [snapped, stale],
  );
  const snappedGeojson = useMemo(
    () => (snapped && (snapped.status === "success" || snapped.status === "partial") && !stale
      ? snapped.geojson : null),
    [snapped, stale],
  );
```

(c) In `snap()`, replace the status-message block so `partial` produces an honest message. The block currently handles `unavailable` and `failed`; make it:
```typescript
      if (res.status === "unavailable") {
        setMessage(
          "Trail snapping unavailable (no routing provider configured). " +
          "You can still save this as a manual, unsnapped route.",
        );
      } else if (res.status === "failed") {
        setMessage(
          (res.message || "Trail snapping failed.") +
          " You can still save this as a manual route.",
        );
      } else if (res.status === "partial") {
        const md = (res.metadata || {}) as { trail_segments?: number; bridged_segments?: number };
        const bits: string[] = [];
        if (md.trail_segments) bits.push(`${md.trail_segments} via trail data`);
        if (md.bridged_segments) {
          bits.push(`${md.bridged_segments} straight bridge${md.bridged_segments > 1 ? "s" : ""} (no trail data)`);
        }
        setMessage(
          `Partially snapped${bits.length ? ": " + bits.join(", ") : ""}. ` +
          "Straight bridges are guesses — verify them before relying on this route.",
        );
      } else {
        setMessage(null);
      }
```

(d) Add `snappedGeojson` to the returned object (next to `snappedPoints`):
```typescript
    manualPoints, snappedPoints, snappedGeojson,
```

(`save()` needs no change — `snappedPoints` is non-null for `partial`, so it already saves the snapped geometry with `source: "openrouteservice"`.)

- [ ] **Step 3: Type-check and tests**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx tsc --noEmit && npx vitest run 2>&1 | tail -5`
Expected: tsc clean; vitest passes.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types.ts frontend/src/hooks/useRouteBuilder.ts
git commit -m "feat(trail-gap-fill): frontend partial-snap handling + snappedGeojson"
```

---

## Task 5: Map bridge styling + panel stats

**Files:**
- Modify: `frontend/src/components/MapView.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/RouteBuilder.tsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Consumes: `rb.snappedGeojson` (FeatureCollection with `properties.mode` ∈ `snapped|bridge`); `rb.snapped.metadata` (`providers_used`, `bridged_segments`, `trail_segments`).
- Produces: a `route-builder-line-bridge` MapLibre layer (dashed red); panel lines showing sources used + bridged count.

- [ ] **Step 1: Add the bridge prop + layer to MapView**

In `frontend/src/components/MapView.tsx`:

(a) Add to the `Props` interface (next to the other route props):
```typescript
  routeSnappedGeojson?: GeoJSON.FeatureCollection | GeoJSON.Feature | null;
```

(b) Add it to the destructuring with a default:
```typescript
  routeMode = false, routeWaypoints = [], routeSnappedPoints = null,
  routeSnappedGeojson = null,
  onRouteAddWaypoint, onRouteMoveWaypoint,
```

(c) In `addOverlaySources`, immediately AFTER the `route-builder-line-snapped` layer, add a bridge layer:
```typescript
    map.addLayer({
      id: "route-builder-line-bridge", type: "line", source: "route-builder-line",
      filter: ["==", ["get", "kind"], "bridge"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#d23b3b", "line-width": 3, "line-dasharray": [1.5, 1.5], "line-opacity": 0.95 },
    });
```

(d) Replace `syncRouteLine` so it prefers the per-segment server geojson (tagging features `kind` from `mode`) and falls back to the flat snapped points:
```typescript
  function syncRouteLine() {
    const feats: GeoJSON.Feature[] = [];
    if (routeWaypoints.length >= 2) {
      feats.push({
        type: "Feature",
        geometry: { type: "LineString", coordinates: routeWaypoints.map((w) => [w.lon, w.lat]) },
        properties: { kind: "manual" },
      });
    }
    const fc = routeSnappedGeojson && (routeSnappedGeojson as GeoJSON.FeatureCollection).type === "FeatureCollection"
      ? (routeSnappedGeojson as GeoJSON.FeatureCollection)
      : null;
    if (fc) {
      for (const f of fc.features) {
        const mode = (f.properties as { mode?: string } | null)?.mode;
        feats.push({ ...f, properties: { kind: mode === "bridge" ? "bridge" : "snapped" } });
      }
    } else if (routeSnappedPoints && routeSnappedPoints.length >= 2) {
      feats.push({
        type: "Feature",
        geometry: { type: "LineString", coordinates: routeSnappedPoints.map((p) => [p[1], p[0]]) },
        properties: { kind: "snapped" },
      });
    }
    setData("route-builder-line", { type: "FeatureCollection", features: feats });
  }
```

(e) Add `routeSnappedGeojson` to the route-line effect deps:
```typescript
  useEffect(() => { if (readyRef.current) syncRouteLine(); }, [routeWaypoints, routeSnappedPoints, routeSnappedGeojson]);
```

- [ ] **Step 2: Pass the geojson from App**

In `frontend/src/App.tsx`, in the `<MapView ... />` usage, add after `routeSnappedPoints={rb.snappedPoints}`:
```typescript
              routeSnappedGeojson={rb.snappedGeojson}
```

- [ ] **Step 3: Show sources + bridged count in the panel**

In `frontend/src/components/RouteBuilder.tsx`, inside the `rb-stats` grid (after the existing Provider stat `<div>`), add a sources/gaps line driven by metadata when a snap exists:
```typescript
            {isSnapped && rb.snapped && (
              <div><span className="rb-k">Sources</span><span className="rb-v">
                {((rb.snapped.metadata as { providers_used?: string[] })?.providers_used || []).join(", ") || "-"}
              </span></div>
            )}
            {isSnapped && rb.snapped && ((rb.snapped.metadata as { bridged_segments?: number })?.bridged_segments ?? 0) > 0 && (
              <div><span className="rb-k">Gaps bridged</span><span className="rb-v">
                {(rb.snapped.metadata as { bridged_segments?: number }).bridged_segments}
              </span></div>
            )}
```

- [ ] **Step 4: Add a tiny legend note for the dashed-red bridge (CSS optional)**

In `frontend/src/index.css`, no new rule is strictly required, but add a small helper used by the disclaimer area if desired (skip if not needed). No change required for functionality.

- [ ] **Step 5: Type-check and build**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -5`
Expected: tsc clean; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/MapView.tsx frontend/src/App.tsx frontend/src/components/RouteBuilder.tsx frontend/src/index.css
git commit -m "feat(trail-gap-fill): distinct bridge styling + source/gap stats"
```

---

## Task 6: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Backend suite**

Run: `cd c:\Users\jacob\summit-signal/backend && python -m pytest tests/ -q`
Expected: all pass (including `tests/test_trail_gap_fill.py` and the unchanged `tests/test_route_builder.py`).

- [ ] **Step 2: Frontend build + tests**

Run: `cd c:\Users\jacob\summit-signal/frontend && npx tsc --noEmit && npm run build 2>&1 | tail -3 && npx vitest run 2>&1 | tail -5`
Expected: tsc clean; build succeeds; vitest passes.

- [ ] **Step 3: Manual smoke (optional, requires both servers + an ORS key)**

With backend + frontend running, logged in, an ORS key set, and (ideally) `SUMMIT_SIGNAL_TRAILS_URL` pointing at a service covering your test area:
1. Build a route whose waypoints straddle a trail not in OSM (the Mt. Rainier case).
2. Snap to trails. Expect a mostly-solid snapped line with any unroutable leg shown as a dashed-red bridge (or solid where trail data filled it), and the panel showing "Sources" and "Gaps bridged".
3. Save — the route renders via the existing GPX path and a condition check uses its bbox.
4. Confirm a fully-routable route still snaps entirely via ORS (status success, no bridges), and that with no ORS key the panel still falls back to manual saving.

- [ ] **Step 4: Final commit (only if verification fixes were needed)**

```bash
git add -A
git commit -m "test(trail-gap-fill): verification pass"
```

---

## Self-Review Notes (author)

- **Spec coverage:** Layered orchestration → Task 3; non-OSM trail source → Task 2; trail-network trace → Task 1; response shape (partial/segments/geojson) → Tasks 3 (backend) + 4 (types); frontend partial handling → Task 4; bridge styling + panel stats → Task 5; testing → Tasks 1-3 + 6; env docs → Task 2.
- **No regression:** whole-route ORS success path preserved (length from ORS summary; bbox from points) so `test_snap_success_with_mocked_ors` stays green; `unavailable` path unchanged.
- **Type consistency:** envelope keys (`status, message, provider, profile, points, geojson, length_miles, bbox, metadata, segments`) match `RouteSnapResponse`; `snap_leg`/`fetch_trail_lines` signatures match their callers in `routing_provider`; `snappedGeojson` produced by the hook and consumed by MapView via `routeSnappedGeojson`; geojson `properties.mode` (`snapped|bridge`) mapped to MapView `kind` (`snapped|bridge`).
- **Never-raise:** `snap_route` wraps the orchestration in try/except; `fetch_trail_lines` and `snap_leg` return `[]`/`None` on failure.
- **No new deps:** Dijkstra + geometry hand-rolled.
```
