"""Pure geometry for the route builder. No network, no DB.

Points are [lat, lon, ele_ft|None] (same convention as gpx_parser). Waypoints
are (lat, lon) tuples. bbox arrays are [minLon, minLat, maxLon, maxLat]; the
storage form mirrors GpxRoute.bbox_json: {"west","south","east","north"}."""
from __future__ import annotations

from .gpx_parser import _haversine_miles


def validate_points(points: list) -> None:
    """Raise ValueError if points is not a usable route."""
    if not points or len(points) < 2:
        raise ValueError("At least two route points are required")
    for p in points:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            raise ValueError("Each point must be [lat, lon, ele?]")
        lat, lon = p[0], p[1]
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            raise ValueError("Point lat/lon must be numbers")
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            raise ValueError(f"Point out of range: {lat}, {lon}")


def haversine_length_miles(points: list) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += _haversine_miles(a[0], a[1], b[0], b[1])
    return round(total, 2)


def bbox_from_points(points: list) -> dict:
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    minlon, minlat, maxlon, maxlat = min(lons), min(lats), max(lons), max(lats)
    return {
        "array": [minlon, minlat, maxlon, maxlat],
        "store": {"west": minlon, "south": minlat, "east": maxlon, "north": maxlat},
    }


def points_from_waypoints(waypoints: list) -> list:
    """[(lat, lon), ...] -> [[lat, lon, None], ...]"""
    return [[w[0], w[1], None] for w in waypoints]
