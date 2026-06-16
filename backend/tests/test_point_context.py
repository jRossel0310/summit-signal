"""Route tests for GET /map/point-context. Offline: both network providers are
monkeypatched. Public endpoint (no auth)."""
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "pc.db"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import elevation as elevation_mod  # noqa: E402
from app.providers import placename as placename_mod  # noqa: E402
from app.providers import aggregator  # noqa: E402

_cm = TestClient(app)
client = _cm.__enter__()


def teardown_module(_m):
    _cm.__exit__(None, None, None)


class _Resp:
    def __init__(self, p):
        self._p = p
    def raise_for_status(self):
        return None
    def json(self):
        return self._p


class _FakeClient:
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def get(self, url, params=None):
        if "epqs" in url:
            return _Resp({"value": 3186.0})
        if "reverse" in url:
            return _Resp({"display_name": "Near Pingora, WY"})
        return _Resp({})


def _patch(monkeypatch):
    aggregator.clear_cache()
    monkeypatch.setattr(elevation_mod, "http_client", lambda: _FakeClient())
    monkeypatch.setattr(placename_mod, "http_client", lambda: _FakeClient())
    from app.providers import current_weather as _cw, snow as _snow, freeze_thaw as _ft
    from app.schemas import ConnectorOutput as _CO
    monkeypatch.setattr(_cw, "http_client", lambda: _FakeClient())
    monkeypatch.setattr(_snow, "http_client", lambda: _FakeClient())
    monkeypatch.setattr(_ft.nws_weather, "run", lambda ctx: _CO(
        connector_name="nws_weather", status="success",
        normalized={"hourly_sample": [], "high_f": None, "low_f": None}))


def test_point_context_returns_sections(monkeypatch):
    _patch(monkeypatch)
    r = client.get("/map/point-context", params={"lat": 40.0, "lon": -105.0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["place_name"] == "Near Pingora, WY"
    elev = next(s for s in body["sections"] if s["layer_id"] == "elevation")
    assert elev["status"] == "ok"
    assert elev["data"]["elevation_ft"] == round(3186.0 * 3.28084)


def test_point_context_no_auth_required(monkeypatch):
    _patch(monkeypatch)
    r = client.get("/map/point-context", params={"lat": 44.0, "lon": -110.0})
    assert r.status_code == 200   # public, like the map


def test_point_context_rejects_bad_coords():
    r = client.get("/map/point-context", params={"lat": 999, "lon": -105.0})
    assert r.status_code == 400


def test_point_context_unknown_layer_id_ignored(monkeypatch):
    _patch(monkeypatch)
    r = client.get("/map/point-context", params={"lat": 40.0, "lon": -105.0, "layers": "nope"})
    assert r.status_code == 200
    ids = {s["layer_id"] for s in r.json()["sections"]}
    assert "nope" not in ids and "elevation" in ids
