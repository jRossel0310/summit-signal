"""Snow point provider — snow depth + recent snowfall from Open-Meteo.

Opt-in (layer-gated): only fetched when the "Snow depth" layer is enabled, so it
stays well under Open-Meteo's free per-IP rate limit. On failure it degrades to a
clean message (never a raw upstream URL) and, because it returns ``error`` status,
the aggregator caches it only briefly so a transient 429 self-heals."""
from __future__ import annotations
import httpx
from ..connectors.base import http_client, utcnow_iso
from .base import ProviderContext, ProviderResult, ok, error

URL = "https://api.open-meteo.com/v1/forecast"
M_TO_IN = 39.3701


class SnowProvider:
    id = "snow"
    title = "Snow"
    requires_key = None
    always_on = False   # opt-in via the "Snow depth" layer toggle

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
        except httpx.HTTPStatusError as e:
            if e.response is not None and e.response.status_code == 429:
                return error(self.id, self.title, "Snow data is rate-limited right now — try again shortly.")
            return error(self.id, self.title, "Snow data is unavailable right now.")
        except Exception:  # noqa: BLE001 — keep the card clean; never surface a raw URL
            return error(self.id, self.title, "Snow data is unavailable right now.")
