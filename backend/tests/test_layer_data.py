"""Viewport layer-data dispatch + cache. Offline (connectors mocked)."""
from app.services import layer_data
from app.schemas import ConnectorOutput

BBOX = {"west": -106.0, "south": 39.0, "east": -105.0, "north": 40.0}


def test_fires_to_geojson(monkeypatch):
    layer_data.clear_cache()
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "k")
    monkeypatch.setattr(layer_data.nasa_firms, "run", lambda ctx: ConnectorOutput(
        connector_name="nasa_firms", status="success",
        normalized={"detections": [{"latitude": 39.5, "longitude": -105.5,
                                     "confidence": "high", "acq_date": "2026-06-15"}]}))
    out = layer_data.layer_features("fires", BBOX)
    assert out["status"] == "ok"
    f = out["features"][0]
    assert f["geometry"]["type"] == "Point"
    assert f["geometry"]["coordinates"] == [-105.5, 39.5]


def test_fires_needs_key(monkeypatch):
    layer_data.clear_cache()
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "")
    out = layer_data.layer_features("fires", BBOX)
    assert out["status"] == "needs_key" and out["features"] == []


def test_cache_prevents_refetch(monkeypatch):
    layer_data.clear_cache()
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "k")
    calls = {"n": 0}
    def _run(ctx):
        calls["n"] += 1
        return ConnectorOutput(connector_name="nasa_firms", status="success", normalized={"detections": []})
    monkeypatch.setattr(layer_data.nasa_firms, "run", _run)
    layer_data.layer_features("fires", BBOX)
    layer_data.layer_features("fires", BBOX)
    assert calls["n"] == 1


def test_unknown_layer():
    out = layer_data.layer_features("nope", BBOX)
    assert out["status"] == "error" and out["features"] == []
