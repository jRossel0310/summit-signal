"""GPX parser. Extracts track/route points, bounding box, approximate length,
and elevation range from an uploaded .gpx file. Pure stdlib (ElementTree)."""
from __future__ import annotations
import math
import xml.etree.ElementTree as ET


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_gpx(content: bytes) -> dict:
    """Returns {points, bbox, length_miles, min_elevation_ft, max_elevation_ft}.
    points are simplified to at most ~1500 [lat, lon, ele_ft|None] triples."""
    root = ET.fromstring(content)
    points: list[list] = []
    for el in root.iter():
        if _strip_ns(el.tag) in ("trkpt", "rtept", "wpt"):
            try:
                lat = float(el.attrib["lat"]); lon = float(el.attrib["lon"])
            except (KeyError, ValueError):
                continue
            ele_ft = None
            for child in el:
                if _strip_ns(child.tag) == "ele" and child.text:
                    try:
                        ele_ft = float(child.text) * 3.28084
                    except ValueError:
                        pass
            points.append([lat, lon, round(ele_ft, 1) if ele_ft is not None else None])
    if not points:
        raise ValueError("No track, route, or waypoint coordinates found in GPX file")

    lats = [p[0] for p in points]; lons = [p[1] for p in points]
    bbox = {"west": min(lons), "south": min(lats), "east": max(lons), "north": max(lats)}

    length = 0.0
    for a, b in zip(points, points[1:]):
        length += _haversine_miles(a[0], a[1], b[0], b[1])

    eles = [p[2] for p in points if p[2] is not None]
    min_ele = round(min(eles)) if eles else None
    max_ele = round(max(eles)) if eles else None

    # Downsample for storage/display
    if len(points) > 1500:
        step = len(points) // 1500 + 1
        points = points[::step]

    return {
        "points": points,
        "bbox": bbox,
        "length_miles": round(length, 1),
        "min_elevation_ft": min_ele,
        "max_elevation_ft": max_ele,
    }


def _haversine_miles(lat1, lon1, lat2, lon2) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
