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


from app.providers import wildfire as wildfire_mod


def test_wildfire_ok(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "k")
    monkeypatch.setattr(wildfire_mod.nasa_firms, "run", lambda ctx: ConnectorOutput(
        connector_name="nasa_firms", status="success",
        normalized={"count": 3, "nearest_miles": 4.2,
                    "detections": [{"confidence": "high", "distance_miles": 4.2}]}))
    out = wildfire_mod.WildfireProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["nearest_miles"] == 4.2
    assert out.data["count"] == 3


def test_wildfire_empty_when_none(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "k")
    monkeypatch.setattr(wildfire_mod.nasa_firms, "run", lambda ctx: ConnectorOutput(
        connector_name="nasa_firms", status="success",
        normalized={"count": 0, "nearest_miles": None, "detections": []}))
    out = wildfire_mod.WildfireProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "empty"


def test_wildfire_needs_key(monkeypatch):
    monkeypatch.setenv("SUMMIT_SIGNAL_FIRMS_KEY", "")
    out = wildfire_mod.WildfireProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "needs_key"


from app.providers import avalanche as avy_mod


def test_avalanche_in_zone(monkeypatch):
    monkeypatch.setattr(avy_mod.avalanche, "run", lambda ctx: ConnectorOutput(
        connector_name="avalanche", status="success",
        normalized={"in_forecast_zone": True, "zone": {
            "zone_name": "Front Range", "center": "CAIC", "current_danger": "Considerable",
            "forecast_link": "https://avalanche.state.co.us/"}}))
    out = avy_mod.AvalancheProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["danger"] == "Considerable"
    assert "CAIC" in out.data["center"]


def test_avalanche_no_zone(monkeypatch):
    monkeypatch.setattr(avy_mod.avalanche, "run", lambda ctx: ConnectorOutput(
        connector_name="avalanche", status="success",
        normalized={"in_forecast_zone": False, "zone": None}))
    out = avy_mod.AvalancheProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "empty"


from app.providers import current_weather as cw_mod


class _Resp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): return None
    def json(self): return self._p


class _CwClient:
    """points -> observationStations -> stations list -> latest obs."""
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def get(self, url, params=None):
        if "/points/" in url:
            return _Resp({"properties": {"observationStations": "https://api.weather.gov/stations"}})
        if url.endswith("/stations"):
            return _Resp({"features": [{"id": "https://api.weather.gov/stations/KBDU",
                                        "properties": {"name": "Boulder"}}]})
        return _Resp({"properties": {
            "temperature": {"value": 12.0}, "windSpeed": {"value": 18.0},
            "windGust": {"value": 30.0}, "relativeHumidity": {"value": 40.0},
            "textDescription": "Mostly Cloudy"}})


def test_current_weather_ok(monkeypatch):
    monkeypatch.setattr(cw_mod, "http_client", lambda: _CwClient())
    out = cw_mod.CurrentWeatherProvider().fetch(ProviderContext(40.0, -105.27))
    assert out.status == "ok"
    assert out.data["temp_f"] == round(12.0 * 9 / 5 + 32)   # C -> F
    assert out.data["conditions"] == "Mostly Cloudy"
    assert out.data["station"] == "Boulder"


def test_current_weather_never_raises(monkeypatch):
    class _Boom:
        def __enter__(self): raise RuntimeError("down")
        def __exit__(self, *a): return False
    monkeypatch.setattr(cw_mod, "http_client", lambda: _Boom())
    out = cw_mod.CurrentWeatherProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status in ("error", "empty")


from app.providers import snow as snow_mod


def test_snow_ok(monkeypatch):
    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, params=None):
            return _Resp({"current": {"snow_depth": 0.42, "snowfall": 1.5},
                          "daily": {"snowfall_sum": [3.0, 0.0, 0.0]}})
    monkeypatch.setattr(snow_mod, "http_client", lambda: _C())
    out = snow_mod.SnowProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["snow_depth_in"] == round(0.42 * 39.3701)   # m -> in
    assert out.data["recent_snowfall_in"] is not None


def test_snow_empty_when_no_snow(monkeypatch):
    class _C:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url, params=None):
            return _Resp({"current": {"snow_depth": 0.0, "snowfall": 0.0},
                          "daily": {"snowfall_sum": [0.0]}})
    monkeypatch.setattr(snow_mod, "http_client", lambda: _C())
    out = snow_mod.SnowProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status in ("ok", "empty")  # zero snow is a valid "no snow" answer
    assert out.data["snow_depth_in"] == 0


from app.providers import freeze_thaw as ft_mod


def _hourly(temps):
    return [{"time": f"2026-06-15T{h:02d}:00:00", "temperature_f": t} for h, t in enumerate(temps)]


def test_freeze_thaw_counts_hours_below_freezing(monkeypatch):
    # 24 temps: first 6 below freezing, rest above
    temps = [25, 26, 28, 30, 31, 20] + [40] * 18
    monkeypatch.setattr(ft_mod.nws_weather, "run", lambda ctx: ConnectorOutput(
        connector_name="nws_weather", status="success",
        normalized={"hourly_sample": _hourly(temps), "high_f": 55, "low_f": 20}))
    out = ft_mod.FreezeThawProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["hours_below_freezing"] == 6
    assert out.data["overnight_low_f"] is not None
    assert out.data["refreeze"] in ("likely", "marginal", "no")
    assert out.data["morning_warming_f_per_hr"] > 0   # temps rise from 20 to 40


def test_freeze_thaw_empty_without_forecast(monkeypatch):
    monkeypatch.setattr(ft_mod.nws_weather, "run", lambda ctx: ConnectorOutput(
        connector_name="nws_weather", status="failed", normalized={"hourly_sample": []}))
    out = ft_mod.FreezeThawProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "empty"
