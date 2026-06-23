"""Route snapping. Fast path: one OpenRouteService (ORS) request for the whole
route. On failure, snap per-segment, filling each leg with the best available
source: ORS (widened radius) -> non-OSM trail data (trail_source + trail_snap)
-> an honest straight-line bridge. Reads keys/URLs from the environment only.
Never raises: failures come back as a status envelope the frontend can render."""
from __future__ import annotations

import httpx

from .settings_service import get_api_key
from . import route_builder, trail_source, trail_snap

ORS_BASE = "https://api.openrouteservice.org/v2/directions"
PROFILE_MAP = {"hiking": "foot-hiking", "walking": "foot-walking"}
DEFAULT_PROFILE = "hiking"
EXTRA_INFO = ["steepness", "surface", "waytype", "traildifficulty", "osmid"]
USER_AGENT = "SummitSignal/0.2 (trip-planning tool; route builder)"
TIMEOUT = 25.0
METERS_PER_MILE = 1609.344
FT_PER_METER = 3.28084
MAX_WAYPOINTS = 50
LEG_RADII_M = [1000, 5000]   # ORS per-leg snap radii to try in order
TRAIL_BBOX_PAD_DEG = 0.02    # ~2 km padding around a leg when fetching trails


def _envelope(status, provider, profile, message=None, points=None, geojson=None,
              length_miles=None, bbox=None, metadata=None, segments=None):
    return {
        "status": status, "message": message, "provider": provider, "profile": profile,
        "points": points or [], "geojson": geojson, "length_miles": length_miles,
        "bbox": bbox, "metadata": metadata or {}, "segments": segments or [],
    }


def snap_route(waypoints, profile: str = DEFAULT_PROFILE, options: dict | None = None) -> dict:
    """waypoints: [(lat, lon), ...]. Returns the RouteSnapResponse dict shape.
    Never raises."""
    profile = profile if profile in PROFILE_MAP else DEFAULT_PROFILE
    if not waypoints or len(waypoints) < 2:
        return _envelope("failed", "none", profile,
                         message="At least two waypoints are required to snap a route.")
    if len(waypoints) > MAX_WAYPOINTS:
        return _envelope("failed", "none", profile,
                         message=f"Too many waypoints to snap (max {MAX_WAYPOINTS}). "
                                 "Reduce the number of waypoints.")
    key = get_api_key(None, "ors")
    if not key:
        return _envelope("unavailable", "none", profile,
                         message="Trail snapping is not configured. Set SUMMIT_SIGNAL_ORS_KEY "
                                 "on the server to enable it.")
    ors_profile = PROFILE_MAP[profile]
    try:
        # Fast path: the whole route in one request.
        whole = _ors_whole(waypoints, ors_profile, key)
        if whole is not None:
            seg = [{"from": 0, "to": len(waypoints) - 1, "provider": "openrouteservice",
                    "snapped": True, "length_miles": whole["length_miles"]}]
            return _finish(whole["points"], profile, seg, [whole["points"]], ["snapped"])

        # Per-segment fallback.
        legs = [_snap_one_leg(waypoints[i], waypoints[i + 1], ors_profile, key)
                for i in range(len(waypoints) - 1)]
        points = _concat([leg["points"] for leg in legs])
        segments, leg_points, leg_modes = [], [], []
        for i, leg in enumerate(legs):
            segments.append({"from": i, "to": i + 1, "provider": leg["provider"],
                             "snapped": leg["snapped"], "length_miles": leg["length_miles"]})
            leg_points.append(leg["points"])
            leg_modes.append("snapped" if leg["snapped"] else "bridge")
        return _finish(points, profile, segments, leg_points, leg_modes)
    except Exception as e:  # noqa: BLE001
        return _envelope("failed", "openrouteservice", profile,
                         message=f"Route snapping failed: {e}")


def _finish(points, profile, segments, leg_points, leg_modes):
    length = round(sum((s.get("length_miles") or 0.0) for s in segments), 2)
    bbox = route_builder.bbox_from_points(points)["array"] if points else None
    features = []
    for pts, mode in zip(leg_points, leg_modes):
        if len(pts) < 2:
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString",
                         "coordinates": [[p[1], p[0]] for p in pts]},
            "properties": {"mode": mode},
        })
    geojson = {"type": "FeatureCollection", "features": features}
    status = "success" if all(s["provider"] == "openrouteservice" for s in segments) else "partial"
    provider = "openrouteservice" if status == "success" else "mixed"
    metadata = {
        "providers_used": sorted({s["provider"] for s in segments}),
        "bridged_segments": sum(1 for s in segments if s["provider"] == "bridge"),
        "trail_segments": sum(1 for s in segments if s["provider"] == "trail_data"),
        "ors_profile": PROFILE_MAP[profile],
    }
    return _envelope(status, provider, profile, points=points, geojson=geojson,
                     length_miles=length, bbox=bbox, metadata=metadata, segments=segments)


def _snap_one_leg(p1, p2, ors_profile, key):
    res = _ors_leg(p1, p2, ors_profile, key)
    if res is not None:
        return {"points": res["points"], "provider": "openrouteservice",
                "snapped": True, "length_miles": res["length_miles"]}
    bbox = (min(p1[1], p2[1]) - TRAIL_BBOX_PAD_DEG, min(p1[0], p2[0]) - TRAIL_BBOX_PAD_DEG,
            max(p1[1], p2[1]) + TRAIL_BBOX_PAD_DEG, max(p1[0], p2[0]) + TRAIL_BBOX_PAD_DEG)
    lines = trail_source.fetch_trail_lines(bbox)
    traced = trail_snap.snap_leg(p1, p2, lines)
    if traced is not None and len(traced) >= 2:
        return {"points": traced, "provider": "trail_data", "snapped": True,
                "length_miles": route_builder.haversine_length_miles(traced)}
    pts = [[p1[0], p1[1], None], [p2[0], p2[1], None]]
    return {"points": pts, "provider": "bridge", "snapped": False,
            "length_miles": route_builder.haversine_length_miles(pts)}


def _ors_whole(waypoints, ors_profile, key):
    coords = [[lon, lat] for (lat, lon) in waypoints]
    return _ors_request(coords, ors_profile, key)


def _ors_leg(p1, p2, ors_profile, key):
    coords = [[p1[1], p1[0]], [p2[1], p2[0]]]
    for r in LEG_RADII_M:
        res = _ors_request(coords, ors_profile, key, radiuses=[r, r])
        if res is not None:
            return res
    return None


def _ors_request(coords, ors_profile, key, radiuses=None):
    body = {"coordinates": coords, "elevation": True, "extra_info": EXTRA_INFO}
    if radiuses is not None:
        body["radiuses"] = radiuses
    try:
        with httpx.Client(timeout=TIMEOUT, headers={
            "Authorization": key, "User-Agent": USER_AGENT,
            "Content-Type": "application/json", "Accept": "application/geo+json",
        }) as cli:
            resp = cli.post(f"{ORS_BASE}/{ors_profile}/geojson", json=body)
    except Exception:  # noqa: BLE001
        return None
    if resp.status_code != 200:
        return None
    return _extract_ors(resp.json())


def _extract_ors(data):
    features = (data or {}).get("features") or []
    if not features:
        return None
    feat = features[0]
    coords = (feat.get("geometry") or {}).get("coordinates") or []
    if len(coords) < 2:
        return None
    points = []
    for c in coords:
        ele_ft = round(c[2] * FT_PER_METER, 1) if len(c) > 2 and c[2] is not None else None
        points.append([c[1], c[0], ele_ft])
    summary = (feat.get("properties") or {}).get("summary") or {}
    dist_m = summary.get("distance")
    length_miles = (round(dist_m / METERS_PER_MILE, 2) if dist_m is not None
                    else route_builder.haversine_length_miles(points))
    return {"points": points, "length_miles": length_miles}


def _concat(leg_point_lists):
    out = []
    for pts in leg_point_lists:
        for p in pts:
            if out and out[-1][0] == p[0] and out[-1][1] == p[1]:
                continue
            out.append(p)
    return out
