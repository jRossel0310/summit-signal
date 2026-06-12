"""The report must render on partial/missing connector data without crashing,
and print_report must 404 a bad check id."""
import json
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "report.db"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402
from app.services import report_generator  # noqa: E402
from tests.conftest import signup_and_token  # noqa: E402

_cm = TestClient(app)
client = _cm.__enter__()
_T, _U, AUTH = signup_and_token(client, "report@example.com")


def teardown_module(_m):
    _cm.__exit__(None, None, None)


def test_report_survives_partial_weather_and_bands():
    trip = models.Trip(user_id=1, name="Partial", latitude=46.0, longitude=-121.0,
                       start_date="2026-07-01", end_date="2026-07-03")
    check = models.ConditionCheck(trip_id=1, status="complete",
                                  overall_concern_status="No major concerns found",
                                  data_completeness_score=0.8, summary_text="")
    # Weather period missing temperature_f / precip_chance; band missing temp_offset_f.
    check.connector_results = [
        models.ConnectorResult(
            connector_name="nws_weather", status="partial",
            normalized_json=json.dumps({"periods": [{"name": "Tonight"}]})),
        models.ConnectorResult(
            connector_name="elevation_adjusted", status="partial",
            normalized_json=json.dumps({"bands": [{"label": "Summit", "elevation_ft": 14000}]})),
    ]
    check.risk_flags = []
    html = report_generator.generate_report_html(trip, check)  # must not raise
    assert "SummitSignal planning report" in html


def test_report_zero_elevation_not_shown_as_question_mark():
    trip = models.Trip(user_id=1, name="Sea", latitude=36.0, longitude=-121.9,
                       start_date="2026-07-01", end_date="2026-07-03")
    trip.gpx_route = models.GpxRoute(filename="coast.gpx", length_miles=5.0,
                                     min_elevation_ft=0, max_elevation_ft=120)
    html = report_generator.generate_report_html(trip, None)
    assert "0–120 ft" in html  # 0 ft renders as 0, not '?'


def test_print_report_bad_check_id_returns_404():
    trips = client.get("/trips", headers=AUTH).json()
    r = client.get(f"/trips/{trips[0]['id']}/print-report?check_id=999999", headers=AUTH)
    assert r.status_code == 404
