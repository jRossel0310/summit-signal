"""Offline smoke tests: schema, CRUD, GPX parsing, risk engine, summarizer,
report generation. Connectors are exercised with synthetic outputs so tests
pass without network access. Run with:  python -m pytest tests/ -q
"""
import os
import tempfile

os.environ["SUMMIT_SIGNAL_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import ConnectorOutput  # noqa: E402
from app.services import risk_engine, gpx_parser  # noqa: E402
from app.agent import summarizer  # noqa: E402
from tests.conftest import signup_and_token  # noqa: E402

# Entering the context manager runs the FastAPI lifespan, which creates
# tables and seeds the sample trips. Kept open for the whole module.
_client_cm = TestClient(app)
client = _client_cm.__enter__()
_TOKEN, _UID, AUTH = signup_and_token(client, "testapp@example.com")


def teardown_module(_module):
    _client_cm.__exit__(None, None, None)

GPX = b"""<?xml version="1.0"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
<trk><name>Test</name><trkseg>
<trkpt lat="46.7860" lon="-121.7360"><ele>1646</ele></trkpt>
<trkpt lat="46.8000" lon="-121.7300"><ele>2100</ele></trkpt>
<trkpt lat="46.8350" lon="-121.7320"><ele>3072</ele></trkpt>
</trkseg></trk></gpx>"""


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_seeded_trips_and_crud():
    r = client.get("/trips", headers=AUTH)
    assert r.status_code == 200
    assert len(r.json()) >= 4  # seeded on this user's signup
    r = client.post("/trips", headers=AUTH, json={
        "name": "Test trip", "location_name": "Somewhere, WA",
        "latitude": 47.0, "longitude": -121.0,
        "start_date": "2026-07-01", "end_date": "2026-07-03",
        "trip_type": "backpacking",
    })
    assert r.status_code == 200
    tid = r.json()["id"]
    r = client.patch(f"/trips/{tid}", headers=AUTH, json={"notes": "updated"})
    assert r.json()["notes"] == "updated"
    r = client.delete(f"/trips/{tid}", headers=AUTH)
    assert r.status_code == 200


def test_gpx_parse_and_upload():
    parsed = gpx_parser.parse_gpx(GPX)
    assert parsed["length_miles"] > 2
    assert parsed["min_elevation_ft"] and parsed["max_elevation_ft"]
    created = client.post("/trips", headers=AUTH, json={
        "name": "GPX trip", "latitude": 46.8, "longitude": -121.7,
        "start_date": "2026-07-01", "end_date": "2026-07-03", "trip_type": "backpacking"}).json()
    tid = created["id"]
    r = client.post(f"/trips/{tid}/upload-gpx", headers=AUTH,
                    files={"file": ("route.gpx", GPX, "application/gpx+xml")})
    assert r.status_code == 200
    assert r.json()["gpx_route"]["length_miles"] > 2


def test_settings_roundtrip():
    r = client.post("/settings", headers=AUTH, json={"fire_radius_miles": 45})
    assert r.status_code == 200
    assert r.json()["fire_radius_miles"] == 45


def _fake_outputs():
    return [
        ConnectorOutput(connector_name="nws_weather", status="success",
                        source_name="NWS", source_url="https://api.weather.gov",
                        source_timestamp="2099-01-01T00:00:00Z",
                        normalized={
                            "periods": [{"name": "Tonight", "temperature_f": 20,
                                         "wind_speed": "25 to 55 mph", "wind_max_mph": 55,
                                         "precip_chance": 80, "short_forecast": "Snow",
                                         "is_daytime": False, "start_time": "",
                                         "wind_direction": "W", "detailed_forecast": ""}],
                            "alerts": [{"event": "Winter Storm Warning", "severity": "Severe",
                                        "headline": "Heavy snow expected", "url": ""}],
                            "high_f": 20, "low_f": 5, "max_wind_mph": 55,
                            "max_precip_chance": 80, "snow_mentioned": True,
                            "thunder_mentioned": False}),
        ConnectorOutput(connector_name="usgs_elevation", status="success",
                        source_name="USGS", normalized={"elevation_ft": 9000, "elevation_m": 2743},
                        source_timestamp="2099-01-01T00:00:00Z"),
        ConnectorOutput(connector_name="nasa_firms", status="skipped",
                        source_name="NASA FIRMS", error_message="API key needed."),
    ]


def test_risk_engine_and_status_language():
    flags, overall, completeness = risk_engine.evaluate(
        _fake_outputs(), risk_engine_settings(), "mountaineering", {})
    assert overall == "Major concerns found"
    titles = [f["title"] for f in flags]
    assert any("Winter Storm" in t for t in titles)
    assert any("API key needed" in t for t in titles)
    banned = ["safe", "unsafe", "go", "no-go", "approved", "cleared"]
    for f in flags:
        assert f["severity"] in ("info", "moderate", "major", "unknown")
    assert overall in ("No major concerns found", "Some concerns found",
                       "Major concerns found", "Data incomplete", "Source check failed")
    assert 0 <= completeness <= 1


def risk_engine_settings():
    return {"fire_radius_miles": 30, "aqi_moderate_threshold": 101,
            "aqi_major_threshold": 151, "wind_gust_moderate_mph": 30,
            "wind_gust_major_mph": 50, "precip_prob_moderate": 60,
            "cold_low_f": 10, "stale_hours": 24}


def test_rule_based_summary_contains_disclaimer():
    outputs = [o.model_dump() for o in _fake_outputs()]
    flags, _, _ = risk_engine.evaluate(_fake_outputs(), risk_engine_settings(),
                                       "mountaineering", {})
    md, gen = summarizer.summarize(
        {"name": "T", "location_name": "X", "latitude": 46.85, "longitude": -121.76,
         "start_date": "2026-07-01", "end_date": "2026-07-03", "trip_type": "mountaineering"},
        flags, outputs, ["Check permits"], {"ollama_enabled": False})
    assert gen == "rule_based"
    assert summarizer.DISCLAIMER in md
    assert "Manual verification checklist" in md


def test_print_report_route():
    created = client.post("/trips", headers=AUTH, json={
        "name": "Report trip", "latitude": 46.8, "longitude": -121.7,
        "start_date": "2026-07-01", "end_date": "2026-07-03", "trip_type": "general"}).json()
    r = client.get(f"/trips/{created['id']}/print-report", headers=AUTH)
    assert r.status_code == 200
    assert "SummitSignal planning report" in r.text
    assert "does not determine whether a trip is safe" in r.text
