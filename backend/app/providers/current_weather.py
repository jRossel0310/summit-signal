"""Current-weather point provider — nearest NWS station's latest observation."""
from __future__ import annotations
from ..connectors.base import http_client, utcnow_iso
from .base import ProviderContext, ProviderResult, ok, empty, error

POINTS = "https://api.weather.gov/points/{lat:.4f},{lon:.4f}"


def _c_to_f(c):
    return None if c is None else round(c * 9 / 5 + 32)


def _ms_to_mph(ms):
    return None if ms is None else round(ms * 2.23694)


class CurrentWeatherProvider:
    id = "current_weather"
    title = "Current weather"
    requires_key = None
    always_on = True

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        try:
            with http_client() as client:
                pr = client.get(POINTS.format(lat=ctx.latitude, lon=ctx.longitude))
                pr.raise_for_status()
                stations_url = (pr.json().get("properties") or {}).get("observationStations")
                if not stations_url:
                    return empty(self.id, self.title, "No NWS station for this point")
                sr = client.get(stations_url)
                sr.raise_for_status()
                feats = sr.json().get("features") or []
                if not feats:
                    return empty(self.id, self.title, "No nearby NWS station")
                station = feats[0]
                obs = client.get(f"{station['id']}/observations/latest")
                obs.raise_for_status()
                p = obs.json().get("properties") or {}
                return ok(self.id, self.title, data={
                    "temp_f": _c_to_f((p.get("temperature") or {}).get("value")),
                    "wind_mph": _ms_to_mph((p.get("windSpeed") or {}).get("value")),
                    "gust_mph": _ms_to_mph((p.get("windGust") or {}).get("value")),
                    "humidity_pct": round(v) if (v := (p.get("relativeHumidity") or {}).get("value")) is not None else None,
                    "conditions": p.get("textDescription"),
                    "station": (station.get("properties") or {}).get("name"),
                }, source_name="National Weather Service stations",
                   source_url="https://www.weather.gov/", source_timestamp=utcnow_iso())
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
