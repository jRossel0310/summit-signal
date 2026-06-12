"""Cross-user isolation and public-endpoint access."""
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "iso.db"))
os.environ.setdefault("SIGNUP_CODE", "test-invite-code")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from tests.conftest import signup_and_token  # noqa: E402

_cm = TestClient(app)
client = _cm.__enter__()


def teardown_module(_m):
    _cm.__exit__(None, None, None)


def test_new_user_gets_sample_trips():
    _t, _uid, headers = signup_and_token(client, "seed@example.com")
    trips = client.get("/trips", headers=headers).json()
    assert len(trips) == 4  # seeded on signup


def test_protected_endpoints_require_auth():
    assert client.get("/trips").status_code == 401
    assert client.get("/settings").status_code == 401


def test_public_endpoints_need_no_auth():
    assert client.get("/health").status_code == 200
    r = client.post("/search/location", json={"query": "46.85, -121.76"})
    assert r.status_code == 200 and "results" in r.json()


def test_user_cannot_touch_another_users_trip():
    _t1, _u1, h1 = signup_and_token(client, "owner@example.com")
    created = client.post("/trips", headers=h1, json={
        "name": "Mine", "latitude": 47.0, "longitude": -121.0,
        "start_date": "2026-07-01", "end_date": "2026-07-03"}).json()
    tid = created["id"]

    _t2, _u2, h2 = signup_and_token(client, "intruder@example.com")
    assert client.get(f"/trips/{tid}", headers=h2).status_code == 404
    assert client.patch(f"/trips/{tid}", headers=h2, json={"notes": "x"}).status_code == 404
    assert client.delete(f"/trips/{tid}", headers=h2).status_code == 404
    assert client.post(f"/trips/{tid}/run-condition-check", headers=h2).status_code == 404
    # Owner still sees it; intruder's trip list does not include it.
    assert any(t["id"] == tid for t in client.get("/trips", headers=h1).json())
    assert all(t["id"] != tid for t in client.get("/trips", headers=h2).json())
