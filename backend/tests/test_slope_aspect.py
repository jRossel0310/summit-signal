"""Pure slope/aspect math + provider tests. Offline."""
import math
from app.providers.slope_aspect import (
    compute_slope_aspect, slope_bucket_label, aspect_compass,
)


def test_flat_surface_is_zero_slope():
    slope, _aspect = compute_slope_aspect(100, 100, 100, 100, 100, spacing_m=50)
    assert slope == 0.0


def test_east_facing_slope_has_east_aspect():
    # elevation drops toward the east: east lower, west higher -> faces east (~90)
    slope, aspect = compute_slope_aspect(center=100, north=100, east=50, south=100, west=150, spacing_m=50)
    assert slope > 0
    assert abs(aspect - 90.0) < 0.5


def test_north_facing_slope_has_north_aspect():
    # drops toward the north -> faces north (~0/360)
    _slope, aspect = compute_slope_aspect(center=100, north=50, east=100, south=150, west=100, spacing_m=50)
    assert aspect < 0.5 or aspect > 359.5


def test_slope_bucket_labels():
    assert slope_bucket_label(5) == "0–15°"
    assert slope_bucket_label(32) == "30–35°"
    assert slope_bucket_label(40) == "35–45°"
    assert slope_bucket_label(60) == "45°+"


def test_aspect_compass_directions():
    assert aspect_compass(0) == "N"
    assert aspect_compass(90) == "E"
    assert aspect_compass(180) == "S"
    assert aspect_compass(270) == "W"
    assert aspect_compass(45) == "NE"


from app.providers import slope_aspect as sa_mod
from app.providers.base import ProviderContext


class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        return None
    def json(self):
        return self._p


class _OneCallClient:
    """Records calls; returns 5 elevations (center,N,E,S,W) for any request."""
    def __init__(self, elevations):
        self.elevations = elevations
        self.calls = 0
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def get(self, url, params=None):
        self.calls += 1
        return _Resp({"elevation": self.elevations})


def test_provider_ok_single_request(monkeypatch):
    # center,N,E,S,W : east lower than west -> east-facing
    client = _OneCallClient([1000, 1000, 950, 1000, 1050])
    monkeypatch.setattr(sa_mod, "http_client", lambda: client)
    out = sa_mod.SlopeAspectProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["aspect_compass"] == "E"
    assert out.data["slope_deg"] > 0
    assert "°" in out.data["slope_bucket"]
    assert client.calls == 1   # all 5 samples in ONE request


def test_provider_never_raises(monkeypatch):
    class _Boom:
        def __enter__(self): raise RuntimeError("down")
        def __exit__(self, *a): return False
    monkeypatch.setattr(sa_mod, "http_client", lambda: _Boom())
    out = sa_mod.SlopeAspectProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status in ("error", "empty")


def test_provider_empty_when_no_elevations(monkeypatch):
    monkeypatch.setattr(sa_mod, "http_client", lambda: _OneCallClient([]))
    out = sa_mod.SlopeAspectProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status in ("empty", "error")
