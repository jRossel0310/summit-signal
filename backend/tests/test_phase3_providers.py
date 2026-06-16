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


from app.providers import aqi as aqi_mod
from app.providers.base import ProviderContext
from app.schemas import ConnectorOutput


def test_aqi_ok(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_AIRNOW_KEY", "k")
    monkeypatch.setattr(aqi_mod.airnow, "run", lambda ctx: ConnectorOutput(
        connector_name="airnow", status="success", source_name="AirNow",
        normalized={"max_aqi": 142, "readings": [
            {"parameter": "PM2.5", "aqi": 142, "category": "Unhealthy for Sensitive Groups",
             "reporting_area": "Boulder"}]}))
    out = aqi_mod.AqiProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["max_aqi"] == 142
    assert out.data["category"]


def test_aqi_needs_key(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_AIRNOW_KEY", "")
    out = aqi_mod.AqiProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "needs_key"


def test_aqi_never_raises(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_AIRNOW_KEY", "k")
    monkeypatch.setattr(aqi_mod.airnow, "run", lambda ctx: (_ for _ in ()).throw(RuntimeError("x")))
    out = aqi_mod.AqiProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status in ("error", "empty")
