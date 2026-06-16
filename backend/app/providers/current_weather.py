"""Current-weather point provider — nearest *reporting* NWS station's latest
observation. The closest station is often listed but not reporting (404 on its
latest observation), so we walk outward to the first station with usable data."""
from __future__ import annotations
from ..connectors.base import http_client, utcnow_iso
from .base import ProviderContext, ProviderResult, ok, empty, error

POINTS = "https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
MAX_STATIONS = 5   # try the nearest few; many stations don't report a latest obs


def _c_to_f(c):
    return None if c is None else round(c * 9 / 5 + 32)


def _ms_to_mph(ms):
    return None if ms is None else round(ms * 2.23694)


def _latest_observation(client, station_id: str):
    """Latest-observation properties for one station, or None if it has none.
    Many NWS stations are listed but return 404 for /observations/latest — that
    is a non-reporting station, not a failure, so we swallow it and try the next."""
    if not station_id:
        return None
    try:
        obs = client.get(f"{station_id}/observations/latest")
        obs.raise_for_status()
        return obs.json().get("properties") or {}
    except Exception:  # noqa: BLE001 — non-reporting station; caller tries the next
        return None


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
                # The nearest station is frequently non-reporting; walk outward to
                # the first one that actually returns a usable observation.
                for station in feats[:MAX_STATIONS]:
                    p = _latest_observation(client, station.get("id", ""))
                    if not p:
                        continue
                    temp_f = _c_to_f((p.get("temperature") or {}).get("value"))
                    conditions = p.get("textDescription")
                    if temp_f is None and not conditions:
                        continue   # station responded but has no usable data
                    return ok(self.id, self.title, data={
                        "temp_f": temp_f,
                        "wind_mph": _ms_to_mph((p.get("windSpeed") or {}).get("value")),
                        "gust_mph": _ms_to_mph((p.get("windGust") or {}).get("value")),
                        "humidity_pct": round(v) if (v := (p.get("relativeHumidity") or {}).get("value")) is not None else None,
                        "conditions": conditions,
                        "station": (station.get("properties") or {}).get("name"),
                    }, source_name="National Weather Service stations",
                       source_url="https://www.weather.gov/", source_timestamp=utcnow_iso())
                return empty(self.id, self.title, "No current weather reported by nearby NWS stations")
        except Exception:  # noqa: BLE001 — keep the card clean; never surface a raw URL
            return error(self.id, self.title, "Current weather is unavailable right now")
