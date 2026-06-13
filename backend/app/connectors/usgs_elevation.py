"""USGS Elevation Connector.

Uses the USGS Elevation Point Query Service (EPQS); no API key required.
Falls back to the open-meteo elevation API if EPQS is unreachable, since the
elevation value feeds the lapse-rate module and is worth a second attempt.
"""
from __future__ import annotations
from .base import ConnectorContext, http_client, failed, utcnow_iso
from ..schemas import ConnectorOutput

NAME = "usgs_elevation"
SOURCE = "USGS Elevation Point Query Service"
EPQS_URL = "https://epqs.nationalmap.gov/v1/json"


def run(ctx: ConnectorContext) -> ConnectorOutput:
    source_name = SOURCE
    source_url = EPQS_URL
    params = {"x": ctx.longitude, "y": ctx.latitude, "units": "Meters", "wkid": 4326,
              "includeDate": "false"}
    try:
        with http_client() as client:
            meters = None
            raw = None
            try:
                r = client.get(EPQS_URL, params=params)
                r.raise_for_status()
                raw = r.json()
                value = raw.get("value")
                meters = float(value) if value not in (None, "None") else None
            except Exception:  # noqa: BLE001
                meters = None

            if meters is None:
                # Fallback source, clearly labeled. Set the attribution BEFORE the
                # call so a fallback FAILURE is also attributed to Open-Meteo.
                source_name = "Open-Meteo elevation (fallback; USGS EPQS unavailable)"
                source_url = "https://api.open-meteo.com/v1/elevation"
                fb = client.get(
                    source_url,
                    params={"latitude": ctx.latitude, "longitude": ctx.longitude},
                )
                fb.raise_for_status()
                raw = fb.json()
                elevs = raw.get("elevation") or []
                if elevs:
                    meters = float(elevs[0])

            if meters is None:
                return failed(NAME, source_name, source_url, "No elevation value returned")

            feet = meters * 3.28084
            ctx.elevation_ft = feet  # share with elevation-adjusted module
            return ConnectorOutput(
                connector_name=NAME,
                status="success",
                source_name=source_name,
                source_url=source_url,
                source_timestamp=utcnow_iso(),
                raw=raw,
                normalized={"elevation_m": round(meters, 1), "elevation_ft": round(feet, 0)},
            )
    except Exception as e:  # noqa: BLE001
        return failed(NAME, source_name, source_url, str(e))
