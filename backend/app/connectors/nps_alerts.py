"""NPS Alerts Connector.

Finds NPS units near the selected point (via the NPS /parks endpoint, filtered
by state and distance), then pulls active alerts for matching park codes.
Requires a free NPS API key; degrades to "API key needed" when missing. Marks
itself "not applicable" when no NPS unit is within range.
"""
from __future__ import annotations
from .base import ConnectorContext, http_client, failed, skipped, utcnow_iso, haversine_miles
from ..schemas import ConnectorOutput

NAME = "nps_alerts"
SOURCE = "National Park Service API"
BASE = "https://developer.nps.gov/api/v1"
NEAR_MILES = 35.0

# Reverse lookup of state from lat/lon uses the NWS points response when
# available; otherwise we query parks without a state filter (slower, paged).


def run(ctx: ConnectorContext) -> ConnectorOutput:
    key = ctx.api_keys.get("nps", "")
    if not key:
        return skipped(
            NAME, SOURCE,
            "API key needed. Get a free key at nps.gov/subjects/developer and add it in Settings.",
        )
    state = (ctx.shared.get("nws_state") or "").upper()
    try:
        with http_client() as client:
            headers = {"X-Api-Key": key}
            params = {"limit": 500, "fields": ""}
            if state:
                params["stateCode"] = state
            r = client.get(f"{BASE}/parks", params=params, headers=headers)
            r.raise_for_status()
            parks = r.json().get("data", [])
            nearby = []
            for p in parks:
                try:
                    plat, plon = float(p.get("latitude")), float(p.get("longitude"))
                except (TypeError, ValueError):
                    continue
                d = haversine_miles(ctx.latitude, ctx.longitude, plat, plon)
                if d <= NEAR_MILES:
                    nearby.append({"code": p.get("parkCode"), "name": p.get("fullName"),
                                   "distance_miles": round(d, 1), "url": p.get("url")})
            nearby.sort(key=lambda x: x["distance_miles"])
            nearby = nearby[:3]
            if not nearby:
                return ConnectorOutput(
                    connector_name=NAME, status="success", source_name=SOURCE,
                    source_url="https://www.nps.gov/", source_timestamp=utcnow_iso(),
                    normalized={"applicable": False,
                                "note": "Selected location is not near an NPS unit "
                                        f"(searched within {NEAR_MILES:.0f} miles)."},
                )
            alerts = []
            for unit in nearby:
                ar = client.get(f"{BASE}/alerts", params={"parkCode": unit["code"], "limit": 50},
                                headers=headers)
                ar.raise_for_status()
                for a in ar.json().get("data", []):
                    alerts.append({
                        "park": unit["name"],
                        "park_code": unit["code"],
                        "category": a.get("category"),   # Danger, Closure, Caution, Information
                        "title": a.get("title"),
                        "description": (a.get("description") or "")[:1200],
                        "url": a.get("url") or unit.get("url"),
                        "last_indexed": a.get("lastIndexedDate"),
                    })
            normalized = {"applicable": True, "units": nearby, "alerts": alerts}
            return ConnectorOutput(
                connector_name=NAME, status="success", source_name=SOURCE,
                source_url="https://www.nps.gov/planyourvisit/alerts.htm",
                source_timestamp=utcnow_iso(), raw={"alert_count": len(alerts)},
                normalized=normalized,
            )
    except Exception as e:  # noqa: BLE001
        return failed(NAME, SOURCE, "https://www.nps.gov/", str(e))
