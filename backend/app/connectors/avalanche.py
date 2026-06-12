"""Avalanche / Snow Connector (v1: region identification + manual-check link).

Deliberately not a universal forecast scraper. It identifies whether the
selected point falls inside (or near) a professional avalanche forecast zone
using the avalanche.org public map layer, and links the user to that center.
If the network call fails, a small static center list keyed by state keeps the
"which center covers me" answer useful. Region-specific forecast APIs can be
added later behind the same run() interface.
"""
from __future__ import annotations
from .base import ConnectorContext, http_client, failed, utcnow_iso
from ..schemas import ConnectorOutput

NAME = "avalanche"
SOURCE = "Avalanche.org forecast zone map"
MAP_LAYER = "https://api.avalanche.org/v2/public/products/map-layer"
PUBLIC_URL = "https://avalanche.org/"

STATIC_CENTERS = {
    "WA": ("Northwest Avalanche Center (NWAC)", "https://nwac.us/"),
    "OR": ("Central Oregon Avalanche Center / NWAC", "https://www.coavalanche.org/"),
    "CO": ("Colorado Avalanche Information Center (CAIC)", "https://avalanche.state.co.us/"),
    "UT": ("Utah Avalanche Center", "https://utahavalanchecenter.org/"),
    "CA": ("Sierra Avalanche Center / ESAC", "https://www.sierraavalanchecenter.org/"),
    "MT": ("Gallatin NF Avalanche Center / Flathead", "https://www.mtavalanche.com/"),
    "WY": ("Bridger-Teton Avalanche Center", "https://bridgertetonavalanchecenter.org/"),
    "ID": ("Sawtooth / Idaho Panhandle Avalanche Centers", "https://www.sawtoothavalanche.com/"),
    "AK": ("Chugach NF Avalanche Information Center", "https://www.cnfaic.org/"),
    "NH": ("Mount Washington Avalanche Center", "https://www.mountwashingtonavalanchecenter.org/"),
    "NM": ("Taos Avalanche Center", "https://taosavalanchecenter.org/"),
    "NV": ("Sierra Avalanche Center", "https://www.sierraavalanchecenter.org/"),
    "AZ": ("Kachina Peaks Avalanche Center", "https://kachinapeaks.org/"),
}


def _point_in_ring(lat, lon, ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _in_geom(lat, lon, geom) -> bool:
    if not geom:
        return False
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])
    polys = coords if gtype == "MultiPolygon" else [coords] if gtype == "Polygon" else []
    return any(poly and _point_in_ring(lat, lon, poly[0]) for poly in polys)


def run(ctx: ConnectorContext) -> ConnectorOutput:
    winter_relevant = (
        ctx.trip_type == "mountaineering"
        or (ctx.elevation_ft or 0) >= 7000
        or bool((ctx.shared.get("nws_normalized") or {}).get("snow_mentioned"))
    )
    manual_required = ctx.trip_type == "mountaineering" or winter_relevant
    try:
        with http_client() as client:
            r = client.get(MAP_LAYER)
            r.raise_for_status()
            gj = r.json()
            match = None
            for feat in gj.get("features", []):
                if _in_geom(ctx.latitude, ctx.longitude, feat.get("geometry")):
                    p = feat.get("properties", {}) or {}
                    match = {
                        "zone_name": p.get("name"),
                        "center": p.get("center"),
                        "center_id": p.get("center_id"),
                        "center_link": p.get("center_link"),
                        "forecast_link": p.get("link"),
                        "current_danger": p.get("danger"),
                        "travel_advice": (p.get("travel_advice") or "")[:600],
                    }
                    break
            normalized = {
                "in_forecast_zone": match is not None,
                "zone": match,
                "manual_check_required": manual_required,
                "winter_relevant": winter_relevant,
                "note": "Version 1 links to the professional forecast center. "
                        "Always read the full forecast at the center's site before travel.",
            }
            return ConnectorOutput(
                connector_name=NAME, status="success", source_name=SOURCE,
                source_url=(match or {}).get("forecast_link") or PUBLIC_URL,
                source_timestamp=utcnow_iso(), raw=None, normalized=normalized,
            )
    except Exception as e:  # noqa: BLE001
        state = (ctx.shared.get("nws_state") or "").upper()
        center = STATIC_CENTERS.get(state)
        if center:
            normalized = {
                "in_forecast_zone": None,
                "zone": {"center": center[0], "forecast_link": center[1]},
                "manual_check_required": manual_required,
                "winter_relevant": winter_relevant,
                "note": "Avalanche.org map layer was unreachable; nearest known center "
                        "suggested from a built-in list. Verify coverage manually.",
            }
            return ConnectorOutput(
                connector_name=NAME, status="partial", source_name=SOURCE,
                source_url=center[1], source_timestamp=utcnow_iso(),
                normalized=normalized, error_message=str(e)[:300],
            )
        return failed(NAME, SOURCE, PUBLIC_URL, str(e))
