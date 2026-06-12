"""Connector edge cases: zero/negative elevation bands are kept; a fallback
failure in usgs_elevation is labeled as the fallback source, not EPQS."""
from app.connectors.base import ConnectorContext
from app.connectors import elevation_adjusted, usgs_elevation


def _ctx_with_band(trailhead_ft):
    ctx = ConnectorContext(
        latitude=36.0, longitude=-121.0, start_date="2026-07-01", end_date="2026-07-03",
        elevation_bands={"trailhead_ft": trailhead_ft},
        shared={"nws_normalized": {"periods": [{"name": "Today", "temperature_f": 70}]}})
    ctx.elevation_ft = 50.0
    return ctx


def test_zero_elevation_band_is_kept():
    out = elevation_adjusted.run(_ctx_with_band(0))
    labels = [b["label"] for b in out.normalized["bands"]]
    assert "Trailhead" in labels  # 0 ft must not be dropped


def test_negative_elevation_band_is_kept():
    out = elevation_adjusted.run(_ctx_with_band(-282))  # Badwater Basin
    labels = [b["label"] for b in out.normalized["bands"]]
    assert "Trailhead" in labels


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """EPQS call raises; the Open-Meteo fallback returns no elevation."""
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None):
        if "epqs" in url:
            raise RuntimeError("EPQS down")
        return _FakeResp({"elevation": []})  # fallback returns nothing


def test_fallback_failure_is_labeled_as_fallback(monkeypatch):
    monkeypatch.setattr(usgs_elevation, "http_client", lambda: _FakeClient())
    ctx = ConnectorContext(latitude=46.0, longitude=-121.0,
                           start_date="2026-07-01", end_date="2026-07-03")
    out = usgs_elevation.run(ctx)
    assert out.status == "failed"
    assert "Open-Meteo" in out.source_name  # not mislabeled as USGS EPQS
