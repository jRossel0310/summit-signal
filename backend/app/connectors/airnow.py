"""AirNow Air Quality Connector.

Fetches current AQI observations near the point. Requires a free AirNow API
key; degrades to "API key needed" when missing. Current observations from the
AirNow network are preliminary/unvalidated data and are labeled as such.
"""
from __future__ import annotations
from .base import ConnectorContext, http_client, failed, skipped, utcnow_iso
from ..schemas import ConnectorOutput

NAME = "airnow"
SOURCE = "AirNow (US EPA partner network)"
OBS_URL = "https://www.airnowapi.org/aq/observation/latLong/current/"
PUBLIC_URL = "https://www.airnow.gov/"


def run(ctx: ConnectorContext) -> ConnectorOutput:
    key = ctx.api_keys.get("airnow", "")
    if not key:
        return skipped(
            NAME, SOURCE,
            "API key needed. Get a free key at docs.airnowapi.org and add it in Settings.",
        )
    params = {
        "format": "application/json",
        "latitude": ctx.latitude,
        "longitude": ctx.longitude,
        "distance": 75,
        "API_KEY": key,
    }
    try:
        with http_client() as client:
            r = client.get(OBS_URL, params=params)
            r.raise_for_status()
            data = r.json()
            readings = []
            max_aqi = None
            for row in data if isinstance(data, list) else []:
                aqi = row.get("AQI")
                readings.append({
                    "parameter": row.get("ParameterName"),
                    "aqi": aqi,
                    "category": (row.get("Category") or {}).get("Name"),
                    "reporting_area": row.get("ReportingArea"),
                    "state": row.get("StateCode"),
                    "observed": f"{row.get('DateObserved','')} {row.get('HourObserved','')}:00 "
                                f"{row.get('LocalTimeZone','')}".strip(),
                })
                if isinstance(aqi, (int, float)):
                    max_aqi = aqi if max_aqi is None else max(max_aqi, aqi)
            normalized = {
                "max_aqi": max_aqi,
                "readings": readings,
                "note": "AirNow current observations are preliminary and unvalidated; "
                        "values may be revised by reporting agencies.",
            }
            status = "success" if readings else "partial"
            return ConnectorOutput(
                connector_name=NAME, status=status, source_name=SOURCE,
                source_url=PUBLIC_URL, source_timestamp=utcnow_iso(),
                raw=data, normalized=normalized,
                error_message=None if readings else "No monitoring stations within 75 miles",
            )
    except Exception as e:  # noqa: BLE001
        return failed(NAME, SOURCE, PUBLIC_URL, str(e))
