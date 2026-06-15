"""ElevationProvider: USGS EPQS point elevation with Open-Meteo fallback.
Always-on base context for the point dashboard. Never raises."""
from __future__ import annotations
from ..connectors.base import http_client, utcnow_iso
from .base import ProviderContext, ProviderResult, ok, error

EPQS_URL = "https://epqs.nationalmap.gov/v1/json"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/elevation"


class ElevationProvider:
    id = "elevation"
    title = "Elevation"
    requires_key = None
    always_on = True

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        source_name = "USGS Elevation Point Query Service"
        source_url = EPQS_URL
        try:
            with http_client() as client:
                meters = None
                try:
                    r = client.get(EPQS_URL, params={
                        "x": ctx.longitude, "y": ctx.latitude, "units": "Meters",
                        "wkid": 4326, "includeDate": "false"})
                    r.raise_for_status()
                    value = r.json().get("value")
                    meters = float(value) if value not in (None, "None") else None
                except Exception:  # noqa: BLE001
                    meters = None

                if meters is None:
                    source_name = "Open-Meteo elevation (fallback; USGS EPQS unavailable)"
                    source_url = OPEN_METEO_URL
                    fb = client.get(OPEN_METEO_URL, params={
                        "latitude": ctx.latitude, "longitude": ctx.longitude})
                    fb.raise_for_status()
                    elevs = fb.json().get("elevation") or []
                    if elevs:
                        meters = float(elevs[0])

                if meters is None:
                    return error(self.id, self.title, "No elevation value returned")

                feet = meters * 3.28084
                return ok(self.id, self.title,
                          data={"elevation_ft": round(feet), "elevation_m": round(meters, 1)},
                          source_name=source_name, source_url=source_url,
                          source_timestamp=utcnow_iso())
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
