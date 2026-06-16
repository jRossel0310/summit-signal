"""Phase 3 provider tests. Offline — wrapped connectors / http_client mocked."""
from app.providers._wrap import connector_ctx


def test_connector_ctx_loads_env_keys(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "abc")
    monkeypatch.setenv("SUMMIT_SIGNAL_AIRNOW_KEY", "")
    ctx = connector_ctx(40.0, -105.0)
    assert ctx.latitude == 40.0 and ctx.longitude == -105.0
    assert ctx.api_keys["firms"] == "abc"
    assert ctx.api_keys["airnow"] == ""
    assert ctx.settings.get("fire_radius_miles") == 30


def test_connector_ctx_passes_bbox():
    bbox = {"west": -106, "south": 39, "east": -105, "north": 40}
    ctx = connector_ctx(39.5, -105.5, bbox=bbox)
    assert ctx.bbox == bbox
