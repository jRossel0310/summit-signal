"""Route snapping via a pluggable routing provider. First provider:
OpenRouteService (hiking/walking). Reads the key from the environment only
(SUMMIT_SIGNAL_ORS_KEY). Like connectors, this never raises: failures and the
no-key case come back as a status envelope the frontend can render."""
from __future__ import annotations

import httpx

from .settings_service import get_api_key

ORS_BASE = "https://api.openrouteservice.org/v2/directions"
PROFILE_MAP = {"hiking": "foot-hiking", "walking": "foot-walking"}
DEFAULT_PROFILE = "hiking"
EXTRA_INFO = ["steepness", "surface", "waytype", "traildifficulty", "osmid"]
USER_AGENT = "SummitSignal/0.2 (trip-planning tool; route builder)"
TIMEOUT = 25.0
METERS_PER_MILE = 1609.344
FT_PER_METER = 3.28084


def _envelope(status, provider, profile, message=None, points=None,
              geojson=None, length_miles=None, bbox=None, metadata=None):
    return {
        "status": status, "message": message, "provider": provider, "profile": profile,
        "points": points or [], "geojson": geojson, "length_miles": length_miles,
        "bbox": bbox, "metadata": metadata or {},
    }


def snap_route(waypoints: list, profile: str = DEFAULT_PROFILE,
               options: dict | None = None) -> dict:
    """waypoints: [(lat, lon), ...]. Returns the RouteSnapResponse dict shape.
    Never raises."""
    profile = profile if profile in PROFILE_MAP else DEFAULT_PROFILE
    if not waypoints or len(waypoints) < 2:
        return _envelope("failed", "none", profile,
                         message="At least two waypoints are required to snap a route.")
    key = get_api_key(None, "ors")
    if not key:
        return _envelope(
            "unavailable", "none", profile,
            message="Trail snapping is not configured. Set SUMMIT_SIGNAL_ORS_KEY "
                    "on the server to enable it.")

    ors_profile = PROFILE_MAP[profile]
    coords = [[lon, lat] for (lat, lon) in waypoints]  # ORS expects [lon, lat]
    body = {"coordinates": coords, "elevation": True, "extra_info": EXTRA_INFO}
    try:
        with httpx.Client(timeout=TIMEOUT, headers={
            "Authorization": key,
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/geo+json",
        }) as cli:
            resp = cli.post(f"{ORS_BASE}/{ors_profile}/geojson", json=body)
        if resp.status_code != 200:
            return _envelope("failed", "openrouteservice", profile,
                             message=f"Routing provider error ({resp.status_code}). "
                                     f"{resp.text[:200]}")
        return _parse_ors_geojson(resp.json(), profile, ors_profile)
    except Exception as e:  # noqa: BLE001
        return _envelope("failed", "openrouteservice", profile,
                         message=f"Could not reach routing provider: {e}")


def _parse_ors_geojson(data: dict, profile: str, ors_profile: str) -> dict:
    features = (data or {}).get("features") or []
    if not features:
        return _envelope("failed", "openrouteservice", profile,
                         message="Routing provider returned no route.")
    feat = features[0]
    coords = (feat.get("geometry") or {}).get("coordinates") or []  # [lon, lat, ele_m]
    points = []
    for c in coords:
        ele_ft = round(c[2] * FT_PER_METER, 1) if len(c) > 2 and c[2] is not None else None
        points.append([c[1], c[0], ele_ft])
    props = feat.get("properties") or {}
    summary = props.get("summary") or {}
    dist_m = summary.get("distance")
    length_miles = round(dist_m / METERS_PER_MILE, 2) if dist_m is not None else None
    bbox = data.get("bbox") or feat.get("bbox")  # may carry elevation as [.. , minEle, maxEle]
    bbox = list(bbox[:4]) if bbox else None
    metadata = {
        "provider": "openrouteservice",
        "ors_profile": ors_profile,
        "extras": list((props.get("extras") or {}).keys()),
        "ascent": summary.get("ascent"),
        "descent": summary.get("descent"),
    }
    return _envelope("success", "openrouteservice", profile, points=points,
                     geojson=data, length_miles=length_miles, bbox=bbox, metadata=metadata)
