"""update_trip must be able to clear optional fields; get_settings must keep
the typed default when a stored value is unparseable."""
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "rs.db"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402
from app.services.settings_service import get_settings  # noqa: E402

_cm = TestClient(app)
client = _cm.__enter__()


def teardown_module(_m):
    _cm.__exit__(None, None, None)


def test_update_trip_can_clear_elevation_bands():
    r = client.post("/trips", json={
        "name": "Clearable", "latitude": 47.0, "longitude": -121.0,
        "start_date": "2026-07-01", "end_date": "2026-07-03",
        "elevation_bands": {"trailhead_ft": 1000, "mid_ft": 3000, "high_ft": 6000}})
    tid = r.json()["id"]
    assert r.json()["elevation_bands"] is not None
    r2 = client.patch(f"/trips/{tid}", json={"elevation_bands": None})
    assert r2.status_code == 200
    assert r2.json()["elevation_bands"] is None


def test_get_settings_keeps_default_on_unparseable_value(session):
    session.add(models.AppSetting(key="connectors_enabled", value="not-json{"))
    session.commit()
    out = get_settings(session)
    # Falls back to the default dict, not the raw string.
    assert isinstance(out["connectors_enabled"], dict)
    assert out["connectors_enabled"].get("nws_weather") is True
