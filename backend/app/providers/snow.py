"""Snow point provider — snow depth + recent snowfall from Open-Meteo (free)."""
from __future__ import annotations
from ..connectors.base import http_client, utcnow_iso
from .base import ProviderContext, ProviderResult, ok, error

URL = "https://api.open-meteo.com/v1/forecast"
M_TO_IN = 39.3701


class SnowProvider:
    id = "snow"
    title = "Snow"
    requires_key = None
    always_on = True

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        try:
            with http_client() as client:
                r = client.get(URL, params={
                    "latitude": ctx.latitude, "longitude": ctx.longitude,
                    "current": "snow_depth,snowfall", "daily": "snowfall_sum",
                    "forecast_days": 1, "past_days": 2, "timezone": "auto"})
                r.raise_for_status()
                j = r.json()
                depth_m = (j.get("current") or {}).get("snow_depth")
                recent = sum(x for x in ((j.get("daily") or {}).get("snowfall_sum") or [])
                             if isinstance(x, (int, float)))
                return ok(self.id, self.title, data={
                    "snow_depth_in": round((depth_m or 0) * M_TO_IN),
                    "recent_snowfall_in": round(recent, 1),
                }, source_name="Open-Meteo (snow depth / snowfall)",
                   source_url="https://open-meteo.com/", source_timestamp=utcnow_iso())
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
