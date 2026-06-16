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
    _, _, other = signup_and_token(client, "rb-intruder@example.com")
    r = client.post(f"/trips/{trip_id}/built-route", headers=other, json={
        "name": "Hijack", "points": [[46.0, -121.0, None], [46.1, -121.1, None]],
        "source": "manual"})
    assert r.status_code == 404
