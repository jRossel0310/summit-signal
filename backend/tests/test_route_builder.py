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
