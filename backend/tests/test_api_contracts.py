"""Frontend/backend API contract tests.

The React client expects specific response shapes. These shapes were mismatched
and caused white-screen render crashes (a method call on `undefined`). Each test
below pins the shape the frontend actually consumes.
"""
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "contracts.db"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.agent import jobs  # noqa: E402
from tests.conftest import signup_and_token  # noqa: E402

_cm = TestClient(app)
client = _cm.__enter__()
_T, _U, AUTH = signup_and_token(client, "contracts@example.com")


def teardown_module(_m):
    _cm.__exit__(None, None, None)


def test_search_location_returns_results_envelope():
    # Coordinate query takes the offline path (no Nominatim needed).
    r = client.post("/search/location", json={"query": "46.85, -121.76"})
    assert r.status_code == 200
    body = r.json()
    # Frontend does `const { results } = await api.searchLocation(q)`.
    assert isinstance(body, dict) and "results" in body
    assert isinstance(body["results"], list) and len(body["results"]) == 1
    item = body["results"][0]
    # Frontend renders r.display_name / r.latitude / r.longitude / r.kind.
    assert "display_name" in item
    assert item["latitude"] == 46.85 and item["longitude"] == -121.76
    assert "kind" in item


def _create_trip(name="Contract trip"):
    r = client.post("/trips", headers=AUTH, json={
        "name": name, "latitude": 46.8, "longitude": -121.7,
        "start_date": "2026-07-01", "end_date": "2026-07-03", "trip_type": "general"})
    assert r.status_code == 200
    return r.json()["id"]


def test_get_check_ai_summary_is_object():
    trip_id = _create_trip("Summary trip")
    db = SessionLocal()
    try:
        check = models.ConditionCheck(trip_id=trip_id, status="complete",
                                      summary_text="# Summary\n- point one")
        db.add(check)
        db.commit()
        db.add(models.AiSummary(condition_check_id=check.id, generator="rule_based",
                                summary_markdown="# Summary\n- point one"))
        db.commit()
        cid = check.id
    finally:
        db.close()

    body = client.get(f"/condition-checks/{cid}", headers=AUTH).json()
    # Frontend renders check.ai_summary.summary_text and check.ai_summary.generator.
    assert isinstance(body["ai_summary"], dict)
    assert body["ai_summary"]["summary_text"] == "# Summary\n- point one"
    assert body["ai_summary"]["generator"] == "rule_based"


def test_get_check_ai_summary_null_when_absent():
    trip_id = _create_trip("Null summary trip")
    db = SessionLocal()
    try:
        check = models.ConditionCheck(trip_id=trip_id, status="complete", summary_text=None)
        db.add(check)
        db.commit()
        cid = check.id
    finally:
        db.close()
    body = client.get(f"/condition-checks/{cid}", headers=AUTH).json()
    assert body["ai_summary"] is None


def test_run_condition_check_returns_check_with_id(monkeypatch):
    # Don't actually run the (networked) connector pipeline in a test.
    monkeypatch.setattr(jobs, "_run_check", lambda check_id: None)
    trip_id = _create_trip("Run check trip")
    r = client.post(f"/trips/{trip_id}/run-condition-check", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    # Frontend does `beginPolling(c.id, ...)` with the returned object.
    assert isinstance(body.get("id"), int)
    assert body.get("status") == "running"
