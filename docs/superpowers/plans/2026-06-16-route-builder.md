# Route Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a logged-in user build a route on the map, snap it to trails via OpenRouteService (when configured), preview stats, and save it to a trip so it renders and drives condition checks exactly like an uploaded GPX route.

**Architecture:** Backend adds a pure geometry helper module, an OpenRouteService snapping provider (env-key gated, never raises), and two endpoints (`POST /routes/snap`, `POST /trips/{id}/built-route`) — the save endpoint reuses the existing `GpxRoute` storage path. Frontend adds typed API methods, an isolated `useRouteBuilder` hook holding all route state, a `RouteBuilder` map-overlay panel, and additive `route-builder-*` MapLibre sources/layers wired through `MapView` without disturbing existing behavior.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, httpx, pytest (backend); Vite + React + TypeScript + MapLibre GL (frontend).

---

## File Structure

**Backend (create):**
- `backend/app/services/route_builder.py` — pure geometry: validate points, length, bbox, manual points.
- `backend/app/services/routing_provider.py` — ORS snap provider + `snap_route()`; never raises.
- `backend/app/routes/routes.py` — `/routes/snap` and `/trips/{id}/built-route`.
- `backend/tests/test_route_builder.py` — geometry, snap (unavailable + mocked success), save, ownership, validation.

**Backend (modify):**
- `backend/app/schemas.py` — route builder request/response models.
- `backend/app/services/settings_service.py` — add `"ors"` to `ENV_KEY_MAP`.
- `backend/app/main.py` — register the new router.
- `.env.example`, `README.md` — document `SUMMIT_SIGNAL_ORS_KEY`.

**Frontend (create):**
- `frontend/src/hooks/useRouteBuilder.ts` — all route-building state + actions.
- `frontend/src/components/RouteBuilder.tsx` — map-overlay panel UI.

**Frontend (modify):**
- `frontend/src/types.ts` — `RouteWaypoint`, `RouteSnapRequest`, `RouteSnapResponse`, `BuiltRouteSaveRequest`.
- `frontend/src/lib/api.ts` — `snapRoute`, `saveBuiltRoute`.
- `frontend/src/components/MapView.tsx` — `route-builder-*` sources/layers + route-mode click/drag.
- `frontend/src/App.tsx` — instantiate hook, render panel, wire MapView.
- `frontend/src/index.css` (or the app's main stylesheet) — minimal panel styles.

---

## Task 1: Backend schemas

**Files:**
- Modify: `backend/app/schemas.py` (append a new section before `# ---------- Condition checks ----------` or at end of the Trips section)

- [ ] **Step 1: Add the schema classes**

Append after the `TripOut` class (around line 111) in `backend/app/schemas.py`:

```python
# ---------- Route builder ----------

class RouteWaypoint(BaseModel):
    lat: float
    lon: float


class RouteSnapOptions(BaseModel):
    preferTrails: bool = True
    avoidRoads: bool = True


class RouteSnapRequest(BaseModel):
    waypoints: list[RouteWaypoint] = Field(default_factory=list)
    profile: str = "hiking"  # hiking | walking
    options: Optional[RouteSnapOptions] = None


class RouteSnapResponse(BaseModel):
    status: str  # success | failed | unavailable
    message: Optional[str] = None
    provider: str
    profile: str
    points: list = Field(default_factory=list)        # [[lat, lon, ele_or_null], ...]
    geojson: Any = None                               # FeatureCollection or Feature
    length_miles: Optional[float] = None
    bbox: Optional[list] = None                       # [minLon, minLat, maxLon, maxLat]
    metadata: dict = Field(default_factory=dict)


class BuiltRouteSaveRequest(BaseModel):
    name: str = "Built route"
    points: list = Field(default_factory=list)        # [[lat, lon, ele_or_null], ...]
    bbox: Optional[list] = None                       # [minLon, minLat, maxLon, maxLat]
    length_miles: Optional[float] = None
    source: str = "manual"                            # manual | openrouteservice
    profile: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
```

(`Any`, `Optional`, `Field`, `BaseModel` are already imported at the top of the file.)

- [ ] **Step 2: Verify it imports**

Run: `cd backend && python -c "import app.schemas as s; print(s.RouteSnapRequest, s.BuiltRouteSaveRequest)"`
Expected: prints the two classes with no error.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat(route-builder): add route snap/save schemas"
```

---

## Task 2: Geometry helpers (`route_builder.py`)

**Files:**
- Create: `backend/app/services/route_builder.py`
- Test: `backend/tests/test_route_builder.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_route_builder.py`:

```python
"""Route builder: geometry helpers, snapping (unavailable + mocked success),
and saving a built route to a trip. No live network."""
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "routebuilder.db"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.services import route_builder  # noqa: E402
from app.services import routing_provider  # noqa: E402
from tests.conftest import signup_and_token  # noqa: E402

_cm = TestClient(app)
client = _cm.__enter__()
_T, _U, AUTH = signup_and_token(client, "routebuilder@example.com")


def teardown_module(_m):
    _cm.__exit__(None, None, None)


def _create_trip(headers=AUTH, name="Route trip"):
    r = client.post("/trips", headers=headers, json={
        "name": name, "latitude": 46.8, "longitude": -121.7,
        "start_date": "2026-07-01", "end_date": "2026-07-03", "trip_type": "general"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---- geometry helpers ----
def test_bbox_and_length_on_normal_points():
    points = [[46.0, -121.0, None], [46.1, -121.0, None], [46.1, -121.2, None]]
    route_builder.validate_points(points)  # must not raise
    bbox = route_builder.bbox_from_points(points)
    assert bbox["array"] == [-121.2, 46.0, -121.0, 46.1]
    assert bbox["store"] == {"west": -121.2, "south": 46.0, "east": -121.0, "north": 46.1}
    assert route_builder.haversine_length_miles(points) > 0


def test_points_from_waypoints():
    pts = route_builder.points_from_waypoints([(46.0, -121.0), (46.1, -121.1)])
    assert pts == [[46.0, -121.0, None], [46.1, -121.1, None]]


def test_validate_points_rejects_too_few():
    with pytest.raises(ValueError):
        route_builder.validate_points([[46.0, -121.0]])


def test_validate_points_rejects_out_of_range():
    with pytest.raises(ValueError):
        route_builder.validate_points([[200.0, -121.0], [46.0, -121.0]])
```

- [ ] **Step 2: Run the geometry tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_route_builder.py -k "bbox or waypoints or validate" -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.route_builder'` (or import error from `routing_provider`).

- [ ] **Step 3: Implement `route_builder.py`**

Create `backend/app/services/route_builder.py`:

```python
"""Pure geometry for the route builder. No network, no DB.

Points are [lat, lon, ele_ft|None] (same convention as gpx_parser). Waypoints
are (lat, lon) tuples. bbox arrays are [minLon, minLat, maxLon, maxLat]; the
storage form mirrors GpxRoute.bbox_json: {"west","south","east","north"}."""
from __future__ import annotations

from .gpx_parser import _haversine_miles


def validate_points(points: list) -> None:
    """Raise ValueError if points is not a usable route."""
    if not points or len(points) < 2:
        raise ValueError("At least two route points are required")
    for p in points:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            raise ValueError("Each point must be [lat, lon, ele?]")
        lat, lon = p[0], p[1]
        if lat is None or lon is None:
            raise ValueError("Point lat/lon must not be null")
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            raise ValueError(f"Point out of range: {lat}, {lon}")


def haversine_length_miles(points: list) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += _haversine_miles(a[0], a[1], b[0], b[1])
    return round(total, 2)


def bbox_from_points(points: list) -> dict:
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    minlon, minlat, maxlon, maxlat = min(lons), min(lats), max(lons), max(lats)
    return {
        "array": [minlon, minlat, maxlon, maxlat],
        "store": {"west": minlon, "south": minlat, "east": maxlon, "north": maxlat},
    }


def points_from_waypoints(waypoints: list) -> list:
    """[(lat, lon), ...] -> [[lat, lon, None], ...]"""
    return [[w[0], w[1], None] for w in waypoints]
```

- [ ] **Step 4: Run the geometry tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_route_builder.py -k "bbox or waypoints or validate" -q`
Expected: 4 passed. (The snap/save tests in the file will error on import of `routing_provider` until Task 3 — that's expected; the `-k` filter still collects the whole module, so if collection fails, proceed to Task 3 and run them together.)

> Note: if module collection fails because `app.services.routing_provider` does not exist yet, that is expected. Implement Task 3 next, then run the full file.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/route_builder.py backend/tests/test_route_builder.py
git commit -m "feat(route-builder): geometry helpers + tests"
```

---

## Task 3: Snapping provider (`routing_provider.py`)

**Files:**
- Create: `backend/app/services/routing_provider.py`
- Modify: `backend/app/services/settings_service.py` (add `"ors"` to `ENV_KEY_MAP`)
- Test: `backend/tests/test_route_builder.py` (snap tests already written in Task 2 file)

- [ ] **Step 1: Add the snap tests to the test file**

Append to `backend/tests/test_route_builder.py`:

```python
# ---- snapping ----
def test_snap_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("SUMMIT_SIGNAL_ORS_KEY", raising=False)
    r = client.post("/routes/snap", headers=AUTH, json={
        "waypoints": [{"lat": 46.0, "lon": -121.0}, {"lat": 46.1, "lon": -121.1}],
        "profile": "hiking"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unavailable"
    assert body["provider"] == "none"
    assert body["points"] == []


def test_snap_success_with_mocked_ors(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_ORS_KEY", "test-key")
    fake_geojson = {
        "bbox": [-121.1, 46.0, -121.0, 46.1],
        "features": [{
            "bbox": [-121.1, 46.0, -121.0, 46.1],
            "geometry": {"type": "LineString", "coordinates": [
                [-121.0, 46.0, 1000.0], [-121.05, 46.05, 1100.0], [-121.1, 46.1, 1200.0]]},
            "properties": {"summary": {"distance": 8046.72, "ascent": 200, "descent": 0},
                           "extras": {"steepness": {}, "surface": {}}},
        }],
    }

    class FakeResp:
        status_code = 200
        text = ""

        def json(self):
            return fake_geojson

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(routing_provider.httpx, "Client", FakeClient)
    r = client.post("/routes/snap", headers=AUTH, json={
        "waypoints": [{"lat": 46.0, "lon": -121.0}, {"lat": 46.1, "lon": -121.1}],
        "profile": "hiking"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["provider"] == "openrouteservice"
    assert body["profile"] == "hiking"
    assert len(body["points"]) == 3
    assert body["points"][0][2] == round(1000.0 * 3.28084, 1)   # m -> ft
    assert abs(body["length_miles"] - 5.0) < 0.1                # 8046.72 m -> ~5 mi
    assert body["bbox"] == [-121.1, 46.0, -121.0, 46.1]
```

- [ ] **Step 2: Run the snap tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_route_builder.py -k "snap" -q`
Expected: FAIL — import error for `routing_provider`, or 404 on `/routes/snap` (route not registered yet). Either way, not passing.

- [ ] **Step 3: Add the env key mapping**

In `backend/app/services/settings_service.py`, change `ENV_KEY_MAP` (around line 27) to include ORS:

```python
ENV_KEY_MAP = {
    "firms": "SUMMIT_SIGNAL_FIRMS_KEY",
    "airnow": "SUMMIT_SIGNAL_AIRNOW_KEY",
    "nps": "SUMMIT_SIGNAL_NPS_KEY",
    "ors": "SUMMIT_SIGNAL_ORS_KEY",
}
```

- [ ] **Step 4: Implement `routing_provider.py`**

Create `backend/app/services/routing_provider.py`:

```python
"""Route snapping via a pluggable routing provider. First provider:
OpenRouteService (hiking/walking). Reads the key from the environment only
(SUMMIT_SIGNAL_ORS_KEY). Like connectors, this never raises: failures and the
no-key case come back as a status envelope the frontend can render."""
from __future__ import annotations

import httpx

from .settings_service import get_api_key

ORS_BASE = "https://api.openrouteservice.org/v2/directions"
PROFILE_MAP = {"hiking": "foot-hiking", "walking": "foot-walking"}
DEFAULT_PROFILE = "hiking"
EXTRA_INFO = ["steepness", "surface", "waytype", "traildifficulty", "osmid"]
USER_AGENT = "SummitSignal/0.2 (trip-planning tool; route builder)"
TIMEOUT = 25.0
METERS_PER_MILE = 1609.344
FT_PER_METER = 3.28084


def _envelope(status, provider, profile, message=None, points=None,
              geojson=None, length_miles=None, bbox=None, metadata=None):
    return {
        "status": status, "message": message, "provider": provider, "profile": profile,
        "points": points or [], "geojson": geojson, "length_miles": length_miles,
        "bbox": bbox, "metadata": metadata or {},
    }


def snap_route(waypoints: list, profile: str = DEFAULT_PROFILE,
               options: dict | None = None) -> dict:
    """waypoints: [(lat, lon), ...]. Returns the RouteSnapResponse dict shape.
    Never raises."""
    profile = profile if profile in PROFILE_MAP else DEFAULT_PROFILE
    if not waypoints or len(waypoints) < 2:
        return _envelope("failed", "none", profile,
                         message="At least two waypoints are required to snap a route.")
    key = get_api_key(None, "ors")
    if not key:
        return _envelope(
            "unavailable", "none", profile,
            message="Trail snapping is not configured. Set SUMMIT_SIGNAL_ORS_KEY "
                    "on the server to enable it.")

    ors_profile = PROFILE_MAP[profile]
    coords = [[lon, lat] for (lat, lon) in waypoints]  # ORS expects [lon, lat]
    body = {"coordinates": coords, "elevation": True, "extra_info": EXTRA_INFO}
    try:
        with httpx.Client(timeout=TIMEOUT, headers={
            "Authorization": key,
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/geo+json",
        }) as cli:
            resp = cli.post(f"{ORS_BASE}/{ors_profile}/geojson", json=body)
        if resp.status_code != 200:
            return _envelope("failed", "openrouteservice", profile,
                             message=f"Routing provider error ({resp.status_code}). "
                                     f"{resp.text[:200]}")
        return _parse_ors_geojson(resp.json(), profile, ors_profile)
    except Exception as e:  # noqa: BLE001
        return _envelope("failed", "openrouteservice", profile,
                         message=f"Could not reach routing provider: {e}")


def _parse_ors_geojson(data: dict, profile: str, ors_profile: str) -> dict:
    features = (data or {}).get("features") or []
    if not features:
        return _envelope("failed", "openrouteservice", profile,
                         message="Routing provider returned no route.")
    feat = features[0]
    coords = (feat.get("geometry") or {}).get("coordinates") or []  # [lon, lat, ele_m]
    points = []
    for c in coords:
        ele_ft = round(c[2] * FT_PER_METER, 1) if len(c) > 2 and c[2] is not None else None
        points.append([c[1], c[0], ele_ft])
    props = feat.get("properties") or {}
    summary = props.get("summary") or {}
    dist_m = summary.get("distance")
    length_miles = round(dist_m / METERS_PER_MILE, 2) if dist_m is not None else None
    bbox = data.get("bbox") or feat.get("bbox")  # may carry elevation as [.. , minEle, maxEle]
    bbox = list(bbox[:4]) if bbox else None
    metadata = {
        "provider": "openrouteservice",
        "ors_profile": ors_profile,
        "extras": list((props.get("extras") or {}).keys()),
        "ascent": summary.get("ascent"),
        "descent": summary.get("descent"),
    }
    return _envelope("success", "openrouteservice", profile, points=points,
                     geojson=data, length_miles=length_miles, bbox=bbox, metadata=metadata)
```

- [ ] **Step 5: Run the snap tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_route_builder.py -k "snap" -q`
Expected: still FAIL with 404 on `/routes/snap` (the route is added in Task 4). The provider unit logic is now importable. Proceed to Task 4, then run the full file.

> If you want to verify the provider in isolation now:
> Run: `cd backend && python -c "from app.services.routing_provider import snap_route; print(snap_route([(46.0,-121.0),(46.1,-121.1)]))"`
> Expected: prints an envelope with `'status': 'unavailable'` (no key set).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/routing_provider.py backend/app/services/settings_service.py backend/tests/test_route_builder.py
git commit -m "feat(route-builder): OpenRouteService snapping provider + tests"
```

---

## Task 4: Routes (`/routes/snap`, `/trips/{id}/built-route`)

**Files:**
- Create: `backend/app/routes/routes.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_route_builder.py` (save/ownership tests)

- [ ] **Step 1: Add the save/ownership tests**

Append to `backend/tests/test_route_builder.py`:

```python
# ---- saving a built route ----
def test_save_built_route_creates_and_attaches():
    trip_id = _create_trip(name="Save route trip")
    r = client.post(f"/trips/{trip_id}/built-route", headers=AUTH, json={
        "name": "My built route",
        "points": [[46.0, -121.0, 1000], [46.1, -121.1, 1200]],
        "bbox": [-121.1, 46.0, -121.0, 46.1],
        "length_miles": 5.0, "source": "manual"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gpx_route_id"] is not None
    assert body["gpx_route"]["filename"] == "My built route"
    assert len(body["gpx_route"]["points"]) == 2
    assert body["gpx_route"]["length_miles"] == 5.0
    assert body["gpx_route"]["bbox"] == {
        "west": -121.1, "south": 46.0, "east": -121.0, "north": 46.1}
    assert body["gpx_route"]["min_elevation_ft"] == 1000
    assert body["gpx_route"]["max_elevation_ft"] == 1200


def test_save_built_route_computes_length_and_bbox_when_missing():
    trip_id = _create_trip(name="Auto stats trip")
    r = client.post(f"/trips/{trip_id}/built-route", headers=AUTH, json={
        "name": "Auto", "points": [[46.0, -121.0, None], [46.1, -121.1, None]],
        "source": "manual"})
    assert r.status_code == 200, r.text
    gpx = r.json()["gpx_route"]
    assert gpx["length_miles"] is not None and gpx["length_miles"] > 0
    assert gpx["bbox"] == {"west": -121.1, "south": 46.0, "east": -121.0, "north": 46.1}


def test_save_built_route_rejects_invalid_points():
    trip_id = _create_trip(name="Invalid points trip")
    r = client.post(f"/trips/{trip_id}/built-route", headers=AUTH, json={
        "name": "Bad", "points": [[46.0, -121.0, None]], "source": "manual"})
    assert r.status_code == 400


def test_cannot_save_route_to_another_users_trip():
    trip_id = _create_trip(name="Owner trip")
    _, _, other = signup_and_token(client, "intruder@example.com")
    r = client.post(f"/trips/{trip_id}/built-route", headers=other, json={
        "name": "Hijack", "points": [[46.0, -121.0, None], [46.1, -121.1, None]],
        "source": "manual"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run the full test file to verify failures**

Run: `cd backend && python -m pytest tests/test_route_builder.py -q`
Expected: geometry tests pass; snap + save tests FAIL (404, routes not registered).

- [ ] **Step 3: Implement `routes/routes.py`**

Create `backend/app/routes/routes.py`:

```python
"""Route builder endpoints: snap waypoints to trails, and save a built route to
a trip. Saving reuses the GpxRoute storage path so built routes render and drive
condition checks exactly like an uploaded GPX route."""
from __future__ import annotations
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..schemas import RouteSnapRequest, RouteSnapResponse, BuiltRouteSaveRequest, TripOut
from ..security import get_current_user
from ..services import route_builder
from ..services.routing_provider import snap_route
from .trips import _owned_trip, _trip_out

router = APIRouter()


@router.post("/routes/snap", response_model=RouteSnapResponse)
def snap(body: RouteSnapRequest, user: models.User = Depends(get_current_user)):
    waypoints = [(w.lat, w.lon) for w in body.waypoints]
    options = body.options.model_dump() if body.options else {}
    return RouteSnapResponse(**snap_route(waypoints, body.profile, options))


@router.post("/trips/{trip_id}/built-route", response_model=TripOut)
def save_built_route(trip_id: int, body: BuiltRouteSaveRequest,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    trip = _owned_trip(trip_id, user, db)
    try:
        route_builder.validate_points(body.points)
    except ValueError as e:
        raise HTTPException(400, str(e))

    points = [[p[0], p[1], (p[2] if len(p) > 2 else None)] for p in body.points]
    length = body.length_miles
    if length is None:
        length = route_builder.haversine_length_miles(points)
    if body.bbox and len(body.bbox) >= 4:
        store_bbox = {"west": body.bbox[0], "south": body.bbox[1],
                      "east": body.bbox[2], "north": body.bbox[3]}
    else:
        store_bbox = route_builder.bbox_from_points(points)["store"]
    eles = [p[2] for p in points if p[2] is not None]

    route = models.GpxRoute(
        trip_id=trip_id,
        filename=(body.name or "Built route"),
        points_json=json.dumps(points),
        bbox_json=json.dumps(store_bbox),
        length_miles=length,
        min_elevation_ft=round(min(eles)) if eles else None,
        max_elevation_ft=round(max(eles)) if eles else None,
    )
    db.add(route)
    db.flush()
    trip.gpx_route_id = route.id
    db.commit()
    db.refresh(trip)
    return _trip_out(trip)
```

- [ ] **Step 4: Register the router in `main.py`**

In `backend/app/main.py`, add the import alongside the other route imports (after line 20):

```python
from .routes import routes as route_builder_routes
```

And register it with the other routers (after `app.include_router(map_routes.router)`):

```python
app.include_router(route_builder_routes.router)
```

- [ ] **Step 5: Run the full test file to verify it passes**

Run: `cd backend && python -m pytest tests/test_route_builder.py -q`
Expected: all tests pass.

- [ ] **Step 6: Run the whole backend suite (no regressions)**

Run: `cd backend && python -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/routes.py backend/app/main.py backend/tests/test_route_builder.py
git commit -m "feat(route-builder): snap + save endpoints"
```

---

## Task 5: Backend docs

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] **Step 1: Add the env var to `.env.example`**

In `.env.example`, add under the existing `SUMMIT_SIGNAL_*` keys (after line 8):

```
SUMMIT_SIGNAL_ORS_KEY=
```

And add an explanatory comment block above the backend keys or beside it:

```
# Optional: OpenRouteService API key (free tier) enables in-app route snapping
# to trails (hiking/walking). Leave unset to keep manual, unsnapped route
# building. Routes are planning aids only. https://openrouteservice.org/dev/#/signup
```

- [ ] **Step 2: Add to the README env table**

In `README.md`, add a row to the API-key table (near the existing `SUMMIT_SIGNAL_AIRNOW_KEY` row, ~line 137):

```
| `SUMMIT_SIGNAL_ORS_KEY` | OpenRouteService API key (free) — enables route snapping. Optional; without it route building still works as manual, unsnapped routes. |
```

Also add a short export example near the other `export SUMMIT_SIGNAL_*` lines (~line 66):

```
export SUMMIT_SIGNAL_ORS_KEY=...    # https://openrouteservice.org/dev/#/signup
```

- [ ] **Step 3: Commit**

```bash
git add .env.example README.md
git commit -m "docs(route-builder): document SUMMIT_SIGNAL_ORS_KEY"
```

---

## Task 6: Frontend types

**Files:**
- Modify: `frontend/src/types.ts`

- [ ] **Step 1: Add the types**

Append to `frontend/src/types.ts`:

```typescript
export interface RouteWaypoint {
  lat: number;
  lon: number;
}

export interface RouteSnapRequest {
  waypoints: RouteWaypoint[];
  profile: "hiking" | "walking";
  options?: { preferTrails?: boolean; avoidRoads?: boolean };
}

export interface RouteSnapResponse {
  status: "success" | "failed" | "unavailable";
  message: string | null;
  provider: string;
  profile: string;
  points: [number, number, number | null][]; // [lat, lon, ele_ft|null]
  geojson: GeoJSON.FeatureCollection | GeoJSON.Feature | null;
  length_miles: number | null;
  bbox: number[] | null; // [minLon, minLat, maxLon, maxLat]
  metadata: Record<string, unknown>;
}

export interface BuiltRouteSaveRequest {
  name: string;
  points: [number, number, number | null][];
  bbox: number[] | null;
  length_miles: number | null;
  source: "manual" | "openrouteservice";
  profile?: string | null;
  metadata?: Record<string, unknown>;
}
```

(`GeoJSON` is globally available via `@types/geojson`, already used in `api.ts` and `MapView.tsx`.)

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types.ts
git commit -m "feat(route-builder): frontend route types"
```

---

## Task 7: Frontend API methods

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Extend the type imports**

In `frontend/src/lib/api.ts`, add the new types to the existing `import type { ... } from "../types";` block:

```typescript
import type {
  AppSettings,
  BuiltRouteSaveRequest,
  CheckStatus,
  ConditionCheck,
  ConditionCheckDetail,
  RouteSnapRequest,
  RouteSnapResponse,
  SearchResult,
  SettingsUpdate,
  Trip,
  TripCreate,
  User,
} from "../types";
```

- [ ] **Step 2: Add the API methods**

In the `export const api = { ... }` object, add after `uploadGpx` (after line 112):

```typescript
  snapRoute: (req: RouteSnapRequest) =>
    request<RouteSnapResponse>("/routes/snap", {
      method: "POST", body: JSON.stringify(req),
    }),

  saveBuiltRoute: (tripId: number, req: BuiltRouteSaveRequest) =>
    request<Trip>(`/trips/${tripId}/built-route`, {
      method: "POST", body: JSON.stringify(req),
    }),
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(route-builder): snapRoute + saveBuiltRoute api methods"
```

---

## Task 8: `useRouteBuilder` hook

**Files:**
- Create: `frontend/src/hooks/useRouteBuilder.ts`

- [ ] **Step 1: Implement the hook**

Create `frontend/src/hooks/useRouteBuilder.ts`:

```typescript
import { useCallback, useMemo, useState } from "react";
import { api } from "../lib/api";
import type {
  BuiltRouteSaveRequest, RouteSnapResponse, RouteWaypoint, Trip,
} from "../types";

export interface RouteBuilderState {
  mode: boolean;
  waypoints: RouteWaypoint[];
  snapped: RouteSnapResponse | null;
  stale: boolean;            // waypoints edited since the last successful snap
  busy: boolean;
  message: string | null;
  manualPoints: [number, number, number | null][];
  snappedPoints: [number, number, number | null][] | null;
  toggleMode: () => void;
  addWaypoint: (lat: number, lon: number) => void;
  moveWaypoint: (index: number, lat: number, lon: number) => void;
  undoLast: () => void;
  clear: () => void;
  snap: () => Promise<void>;
  save: (tripId: number) => Promise<Trip | null>;
}

export function useRouteBuilder(): RouteBuilderState {
  const [mode, setMode] = useState(false);
  const [waypoints, setWaypoints] = useState<RouteWaypoint[]>([]);
  const [snapped, setSnapped] = useState<RouteSnapResponse | null>(null);
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const manualPoints = useMemo<[number, number, number | null][]>(
    () => waypoints.map((w) => [w.lat, w.lon, null]),
    [waypoints],
  );
  const snappedPoints = useMemo(
    () => (snapped && snapped.status === "success" && !stale ? snapped.points : null),
    [snapped, stale],
  );

  const toggleMode = useCallback(() => setMode((m) => !m), []);

  const addWaypoint = useCallback((lat: number, lon: number) => {
    setWaypoints((w) => [...w, { lat, lon }]);
    setStale(true);
  }, []);

  const moveWaypoint = useCallback((index: number, lat: number, lon: number) => {
    setWaypoints((w) => w.map((p, i) => (i === index ? { lat, lon } : p)));
    setStale(true);
  }, []);

  const undoLast = useCallback(() => {
    setWaypoints((w) => w.slice(0, -1));
    setStale(true);
  }, []);

  const clear = useCallback(() => {
    setWaypoints([]);
    setSnapped(null);
    setStale(false);
    setMessage(null);
  }, []);

  const snap = useCallback(async () => {
    if (waypoints.length < 2) {
      setMessage("Add at least two waypoints to snap.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const res = await api.snapRoute({
        waypoints,
        profile: "hiking",
        options: { preferTrails: true, avoidRoads: true },
      });
      setSnapped(res);
      setStale(false);
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
      } else {
        setMessage(null);
      }
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [waypoints]);

  const save = useCallback(async (tripId: number): Promise<Trip | null> => {
    if (waypoints.length < 2) {
      setMessage("Add at least two waypoints first.");
      return null;
    }
    const useSnapped = !!snappedPoints && !!snapped;
    const req: BuiltRouteSaveRequest = useSnapped
      ? {
          name: "Snapped route",
          points: snapped!.points,
          bbox: snapped!.bbox,
          length_miles: snapped!.length_miles,
          source: "openrouteservice",
          profile: snapped!.profile,
          metadata: snapped!.metadata,
        }
      : {
          name: "Manual route",
          points: manualPoints,
          bbox: null,
          length_miles: null,
          source: "manual",
          profile: null,
          metadata: {},
        };
    setBusy(true);
    setMessage(null);
    try {
      const trip = await api.saveBuiltRoute(tripId, req);
      clear();
      setMode(false);
      return trip;
    } catch (e) {
      setMessage((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }, [waypoints, snapped, snappedPoints, manualPoints, clear]);

  return {
    mode, waypoints, snapped, stale, busy, message,
    manualPoints, snappedPoints,
    toggleMode, addWaypoint, moveWaypoint, undoLast, clear, snap, save,
  };
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors (the hook is not yet imported anywhere; that's fine).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useRouteBuilder.ts
git commit -m "feat(route-builder): useRouteBuilder state hook"
```

---

## Task 9: `RouteBuilder` panel component

**Files:**
- Create: `frontend/src/components/RouteBuilder.tsx`
- Modify: the app stylesheet (e.g. `frontend/src/index.css`) — minimal panel styles.

- [ ] **Step 1: Implement the component**

Create `frontend/src/components/RouteBuilder.tsx`:

```typescript
import type { RouteBuilderState } from "../hooks/useRouteBuilder";
import type { Trip } from "../types";

interface Props {
  rb: RouteBuilderState;
  loggedIn: boolean;
  selectedTripId: number | null;
  selectedTripName: string | null;
  onSaved: (trip: Trip) => void;
}

const R = 3958.8;
function haversineMiles(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const p1 = (a.lat * Math.PI) / 180;
  const p2 = (b.lat * Math.PI) / 180;
  const dp = ((b.lat - a.lat) * Math.PI) / 180;
  const dl = ((b.lon - a.lon) * Math.PI) / 180;
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function manualMiles(waypoints: { lat: number; lon: number }[]): number {
  let total = 0;
  for (let i = 1; i < waypoints.length; i++) total += haversineMiles(waypoints[i - 1], waypoints[i]);
  return total;
}

export default function RouteBuilder({
  rb, loggedIn, selectedTripId, selectedTripName, onSaved,
}: Props) {
  if (!loggedIn) return null;

  const isSnapped = !!rb.snappedPoints && !!rb.snapped;
  const miles = isSnapped && rb.snapped!.length_miles != null
    ? rb.snapped!.length_miles
    : manualMiles(rb.waypoints);
  const provider = isSnapped ? rb.snapped!.provider : "manual";
  const profile = isSnapped ? rb.snapped!.profile : "-";

  async function handleSave() {
    if (selectedTripId == null) return;
    const trip = await rb.save(selectedTripId);
    if (trip) onSaved(trip);
  }

  return (
    <div className="route-builder-panel">
      <button className="btn small full" onClick={rb.toggleMode}>
        {rb.mode ? "✕ Exit route builder" : "✎ Build route"}
      </button>

      {rb.mode && (
        <div className="route-builder-body">
          <div className="rb-hint">Click the map to add waypoints. Drag a marker to adjust.</div>

          <div className="rb-stats">
            <div><span className="rb-k">Distance</span><span className="rb-v">{miles.toFixed(2)} mi</span></div>
            <div><span className="rb-k">Waypoints</span><span className="rb-v">{rb.waypoints.length}</span></div>
            <div><span className="rb-k">Mode</span><span className="rb-v">{isSnapped ? "snapped" : "manual"}</span></div>
            <div><span className="rb-k">Provider</span><span className="rb-v">{provider}{isSnapped ? ` · ${profile}` : ""}</span></div>
          </div>

          {rb.snapped && rb.stale && (
            <div className="rb-warn">Snapped route is stale — re-snap to update it.</div>
          )}
          {rb.message && <div className="rb-warn">{rb.message}</div>}

          <div className="rb-actions">
            <button className="btn small" disabled={rb.busy || rb.waypoints.length === 0} onClick={rb.undoLast}>Undo last</button>
            <button className="btn small" disabled={rb.busy || rb.waypoints.length === 0} onClick={rb.clear}>Clear</button>
            <button className="btn small" disabled={rb.busy || rb.waypoints.length < 2} onClick={rb.snap}>
              {rb.busy ? "Snapping…" : "Snap to trails"}
            </button>
          </div>

          <button
            className="btn primary small full"
            disabled={rb.busy || rb.waypoints.length < 2 || selectedTripId == null}
            onClick={handleSave}
          >
            {selectedTripId == null
              ? "Select a trip to save"
              : `Save ${isSnapped ? "snapped" : "manual"} route to ${selectedTripName || "trip"}`}
          </button>

          <div className="rb-disclaimer">
            Trail snapping uses available routing/map data and may be incomplete or wrong.
            Verify official maps, access restrictions, permits, seasonal closures, and current
            conditions before relying on this route.
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add minimal styles**

Append to the app stylesheet (`frontend/src/index.css` — confirm the global stylesheet path by checking `main.tsx`'s CSS import; use that file):

```css
.route-builder-panel {
  background: var(--panel, #fbfaf6);
  border: 1px solid var(--line-strong, #d8d2c4);
  border-radius: 4px;
  padding: 8px;
  width: 240px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
  font-size: 12px;
}
.route-builder-body { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; }
.rb-hint { color: var(--ink-soft, #6b6456); font-size: 11px; }
.rb-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px; }
.rb-stats > div { display: flex; justify-content: space-between; gap: 6px; }
.rb-k { color: var(--ink-soft, #6b6456); }
.rb-v { font-family: var(--mono, monospace); }
.rb-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.rb-warn {
  background: #fff4e5; border: 1px solid #f0c98c; color: #8a5a12;
  border-radius: 3px; padding: 6px; font-size: 11px;
}
.rb-disclaimer { color: var(--ink-soft, #6b6456); font-size: 10.5px; line-height: 1.35; }
```

(If the project uses a `.btn.full` modifier already — it does, see `TripForm` — reuse it. The classes above only add what's missing.)

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/RouteBuilder.tsx frontend/src/index.css
git commit -m "feat(route-builder): RouteBuilder panel component"
```

---

## Task 10: MapView integration

**Files:**
- Modify: `frontend/src/components/MapView.tsx`

- [ ] **Step 1: Extend the `Props` interface**

In `frontend/src/components/MapView.tsx`, add to the `interface Props` (after `onSelectTrip` on line 50):

```typescript
  // route builder (additive; all optional so existing usage is unaffected)
  routeMode?: boolean;
  routeWaypoints?: { lat: number; lon: number }[];
  routeSnappedPoints?: [number, number, number | null][] | null;
  onRouteAddWaypoint?: (lat: number, lon: number) => void;
  onRouteMoveWaypoint?: (index: number, lat: number, lon: number) => void;
```

- [ ] **Step 2: Destructure the new props and keep them in a ref**

Update the component signature destructuring (lines 55-58) to include the new props:

```typescript
export default function MapView({
  layerState, trips, selectedTripId, selectedPoint, flyTo, gpxPoints,
  onSelectPoint, onSelectTrip,
  routeMode = false, routeWaypoints = [], routeSnappedPoints = null,
  onRouteAddWaypoint, onRouteMoveWaypoint,
}: Props) {
```

Just after the existing `handlersRef` definition (lines 65-66), add a ref so the stable map `click` handler always sees current route state/handlers:

```typescript
  const routeRef = useRef({ routeMode, onRouteAddWaypoint, onRouteMoveWaypoint });
  routeRef.current = { routeMode, onRouteAddWaypoint, onRouteMoveWaypoint };
  const wpMarkersRef = useRef<maplibregl.Marker[]>([]);
```

- [ ] **Step 3: Branch the map click handler for route mode**

Replace the existing top-level `map.on("click", ...)` handler (lines 97-105) with:

```typescript
    map.on("click", (e) => {
      const feats = map.queryRenderedFeatures(e.point, { layers: ["trips-circle"] });
      if (feats.length > 0) {
        const id = feats[0].properties?.id;
        if (id != null) handlersRef.current.onSelectTrip(Number(id));
        return;
      }
      if (routeRef.current.routeMode) {
        routeRef.current.onRouteAddWaypoint?.(e.lngLat.lat, e.lngLat.lng);
        return;
      }
      handlersRef.current.onSelectPoint(e.lngLat.lat, e.lngLat.lng);
    });
```

- [ ] **Step 4: Add the route-builder sources and layers**

In `addOverlaySources(map)`, after the `gpx-line` layer is added (after line 181) and before the `trips-circle` layer, add:

```typescript
    map.addSource("route-builder-line", { type: "geojson", data: EMPTY_FC });
    map.addLayer({
      id: "route-builder-line-manual", type: "line", source: "route-builder-line",
      filter: ["==", ["get", "kind"], "manual"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#8a5a12", "line-width": 2.2, "line-dasharray": [2, 2], "line-opacity": 0.9 },
    });
    map.addLayer({
      id: "route-builder-line-snapped", type: "line", source: "route-builder-line",
      filter: ["==", ["get", "kind"], "snapped"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#1d6fd8", "line-width": 4, "line-opacity": 0.95 },
    });
    map.addSource("route-builder-waypoints", { type: "geojson", data: EMPTY_FC });
    map.addLayer({
      id: "route-builder-waypoints", type: "circle", source: "route-builder-waypoints",
      paint: {
        "circle-radius": 8, "circle-color": "#1d6fd8",
        "circle-stroke-color": "#fbfaf6", "circle-stroke-width": 2,
      },
    });
    map.addLayer({
      id: "route-builder-labels", type: "symbol", source: "route-builder-waypoints",
      layout: {
        "text-field": ["get", "label"], "text-size": 11,
        "text-font": ["Noto Sans Regular"], "text-allow-overlap": true,
      },
      paint: { "text-color": "#fbfaf6" },
    });
```

- [ ] **Step 5: Add the route-builder sync functions**

Add these functions next to `syncGpx` (after line 269):

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
    if (routeSnappedPoints && routeSnappedPoints.length >= 2) {
      feats.push({
        type: "Feature",
        geometry: { type: "LineString", coordinates: routeSnappedPoints.map((p) => [p[1], p[0]]) },
        properties: { kind: "snapped" },
      });
    }
    setData("route-builder-line", { type: "FeatureCollection", features: feats });
  }

  function syncWaypointMarkers() {
    const map = mapRef.current;
    if (!map) return;
    // numbered labels via the symbol layer
    setData("route-builder-waypoints", {
      type: "FeatureCollection",
      features: routeWaypoints.map((w, i) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [w.lon, w.lat] },
        properties: { label: String(i + 1) },
      })),
    });
    // draggable markers (transparent hit targets on top of the circles)
    for (const m of wpMarkersRef.current) m.remove();
    wpMarkersRef.current = [];
    if (!routeMode) return;
    routeWaypoints.forEach((w, i) => {
      const el = document.createElement("div");
      el.style.width = "20px";
      el.style.height = "20px";
      el.style.borderRadius = "50%";
      el.style.cursor = "grab";
      const marker = new maplibregl.Marker({ element: el, draggable: true })
        .setLngLat([w.lon, w.lat])
        .addTo(map);
      marker.on("dragend", () => {
        const ll = marker.getLngLat();
        routeRef.current.onRouteMoveWaypoint?.(i, ll.lat, ll.lng);
      });
      wpMarkersRef.current.push(marker);
    });
  }
```

- [ ] **Step 6: Call the new syncs and add prop-driven effects**

Update `syncAll()` (line 246) to include the route syncs:

```typescript
  function syncAll() {
    syncTrips(); syncGpx(); syncRouteLine(); syncWaypointMarkers(); syncVisibility(); syncMarker();
  }
```

Add prop-driven effects next to the existing ones (after line 305):

```typescript
  useEffect(() => { if (readyRef.current) syncRouteLine(); }, [routeWaypoints, routeSnappedPoints]);
  useEffect(() => { if (readyRef.current) syncWaypointMarkers(); }, [routeWaypoints, routeMode]);
```

Set the crosshair cursor in route mode (add after line 305 effects):

```typescript
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    map.getCanvas().style.cursor = routeMode ? "crosshair" : "";
  }, [routeMode]);
```

- [ ] **Step 7: Clean up markers on unmount**

In the init effect's cleanup return (lines 134-138), remove the waypoint markers too:

```typescript
    return () => {
      for (const m of wpMarkersRef.current) m.remove();
      wpMarkersRef.current = [];
      map.remove();
      mapRef.current = null;
      readyRef.current = false;
    };
```

- [ ] **Step 8: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/MapView.tsx
git commit -m "feat(route-builder): map sources/layers + route-mode click & drag"
```

---

## Task 11: App wiring

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Import the hook and component**

In `frontend/src/App.tsx`, add imports near the other component imports (after line 21):

```typescript
import RouteBuilder from "./components/RouteBuilder";
import { useRouteBuilder } from "./hooks/useRouteBuilder";
```

- [ ] **Step 2: Instantiate the hook**

Inside `App()`, after `const [layerState, setLayerState] = useState<LayerStateMap>(seedLayerState());` (line 150), add:

```typescript
  const rb = useRouteBuilder();
```

- [ ] **Step 3: Add the saved-route handler**

After the `onTripCreated` function (line 343), add:

```typescript
  function onRouteSaved(trip: Trip) {
    setTrips((prev) => prev.map((t) => (t.id === trip.id ? trip : t)));
    setSelectedTrip(trip);
  }
```

(Updating `selectedTrip` makes the memoized `gpxPoints` recompute, so the saved route renders through the existing `gpx` layer immediately.)

- [ ] **Step 4: Pass route props into MapView**

Update the `<MapView ... />` usage (lines 439-448) to add the route props:

```typescript
            <MapView
              layerState={layerState}
              trips={trips}
              selectedTripId={selectedTrip?.id ?? null}
              selectedPoint={selectedPoint}
              flyTo={flyTo}
              gpxPoints={gpxPoints}
              onSelectPoint={onMapSelect}
              onSelectTrip={(id) => { const t = trips.find((x) => x.id === id); if (t) selectTrip(t); }}
              routeMode={rb.mode}
              routeWaypoints={rb.waypoints}
              routeSnappedPoints={rb.snappedPoints}
              onRouteAddWaypoint={rb.addWaypoint}
              onRouteMoveWaypoint={rb.moveWaypoint}
            />
```

- [ ] **Step 5: Render the RouteBuilder panel on the map**

Add a new map overlay just after the `map-overlay-tr` LayersControl block (after line 459, before the closing `</main>`):

```typescript
            {user && (
              <div className="map-overlay-rb">
                <RouteBuilder
                  rb={rb}
                  loggedIn={!!user}
                  selectedTripId={selectedTrip?.id ?? null}
                  selectedTripName={selectedTrip?.name ?? null}
                  onSaved={onRouteSaved}
                />
              </div>
            )}
```

- [ ] **Step 6: Position the overlay**

Append to the app stylesheet:

```css
.map-overlay-rb {
  position: absolute;
  top: 12px;
  right: 64px; /* clear of the top-right navigation control */
  z-index: 5;
}
@media (max-width: 700px) {
  .map-overlay-rb { right: 12px; top: 56px; }
}
```

(Confirm the existing `.map-overlay-tr` / `.map-overlay-tl` z-index and adjust if the panel overlaps the LayersControl; place it below or left as needed.)

- [ ] **Step 7: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: build succeeds with no errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.tsx frontend/src/index.css
git commit -m "feat(route-builder): wire RouteBuilder + MapView into App"
```

---

## Task 12: Full verification

**Files:** none (verification only)

- [ ] **Step 1: Backend suite**

Run: `cd backend && python -m pytest tests/ -q`
Expected: all tests pass (including `tests/test_route_builder.py`).

- [ ] **Step 2: Frontend build**

Run: `cd frontend && npm run build`
Expected: succeeds, no TypeScript errors.

- [ ] **Step 3: Frontend tests (if present)**

Run: `cd frontend && npm test --silent 2>&1 || echo "no test script"`
Expected: passes, or "no test script" if the project has none.

- [ ] **Step 4: Manual smoke (optional, requires running both servers)**

With the backend + frontend running and a user logged in:
1. Select or create a trip.
2. Click "Build route", click the map a few times → numbered markers + dashed draft line appear.
3. Drag a marker → line updates.
4. Click "Snap to trails":
   - No `SUMMIT_SIGNAL_ORS_KEY` → "unavailable" warning, manual save still offered.
   - With key → solid blue snapped line + distance/provider stats.
5. Click "Save … route to <trip>" → panel closes, route renders via the GPX layer, and a condition check uses the route bbox.
6. Confirm existing GPX upload, terrain/fire layers, and the point dashboard still work.

- [ ] **Step 5: Final commit (if any verification fixes were needed)**

```bash
git add -A
git commit -m "test(route-builder): verification pass"
```

---

## Self-Review Notes (author)

- **Spec coverage:** A (UX) → Tasks 9-11; B (snap backend/ORS) → Tasks 1,3,4; C (save to trip, reuse GpxRoute) → Tasks 1,4; D (stats) → Tasks 4 (backend) + 9 (display); E (frontend types/api/component/MapView) → Tasks 6-11; F (map behavior, stale flag, isolated layers) → Tasks 8,10; G (selected-trip save workflow) → Task 11; H (safety copy verbatim) → Task 9; I (tests) → Tasks 2-4 + 12; J (acceptance) → Task 12. GPX export intentionally deferred (per spec, post-MVP).
- **No schema change:** confirmed — `name`→`filename`, source/metadata not persisted.
- **Type consistency:** `snap_route` envelope keys match `RouteSnapResponse`; `BuiltRouteSaveRequest` fields match the hook's `req`; MapView prop names match App's usage; `snappedPoints`/`manualPoints` consistent across hook + component + MapView.
- **Graceful degradation:** no key → `unavailable` (Task 3), manual save always available (Task 8 `save`).
```
