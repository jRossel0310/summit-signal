"""Fetch non-OSM trail geometry from public ArcGIS REST FeatureServers (USGS
National Map / USFS trails) by bbox. No API key. Never raises — returns [] on
any error. Used to fill OSM gaps in route snapping."""
from __future__ import annotations
import os

import httpx

USER_AGENT = "SummitSignal/0.2 (trip-planning tool; trail snap)"
TIMEOUT = 20.0
MAX_FEATURES = 600

# Verified against the Mt. Rainier bbox during implementation.
# USFS EDW endpoint (/arcx/ path) returned 404 during verification.
# USGS National Map transportation layer 37 ("Trails") returns features for
# the Mt. Rainier area (verified with bbox −122.0,46.7,−121.5,47.0 → 5 features).
# Override with SUMMIT_SIGNAL_TRAILS_URL (comma-separated .../query URLs).
DEFAULT_TRAILS_URLS = [
    "https://carto.nationalmap.gov/arcgis/rest/services/transportation/MapServer/37/query",
    "https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_TrailNFSTrails_01/MapServer/0/query",
]


def _urls() -> list:
    raw = os.environ.get("SUMMIT_SIGNAL_TRAILS_URL", "").strip()
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    return DEFAULT_TRAILS_URLS


def fetch_trail_lines(bbox, urls=None) -> list:
    """bbox: (min_lon, min_lat, max_lon, max_lat). Returns list of polylines
    [[lat, lon], ...]. [] on any error/empty."""
    out: list = []
    for url in (urls if urls is not None else _urls()):
        try:
            out.extend(_fetch_one(url, bbox))
        except Exception:  # noqa: BLE001
            continue
        if len(out) >= MAX_FEATURES:
            break
    return out


def _fetch_one(url, bbox) -> list:
    min_lon, min_lat, max_lon, max_lat = bbox
    params = {
        "geometry": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326", "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "true", "outFields": "*",
        "resultRecordCount": str(MAX_FEATURES),
        "f": "geojson",
    }
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as cli:
        resp = cli.get(url, params=params)
    if resp.status_code != 200:
        return []
    return _parse_geojson(resp.json())


def _parse_geojson(data) -> list:
    lines = []
    for feat in (data or {}).get("features") or []:
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        if gtype == "LineString":
            lines.append([[c[1], c[0]] for c in coords if len(c) >= 2])
        elif gtype == "MultiLineString":
            for part in coords:
                lines.append([[c[1], c[0]] for c in part if len(c) >= 2])
    return [ln for ln in lines if len(ln) >= 2]
