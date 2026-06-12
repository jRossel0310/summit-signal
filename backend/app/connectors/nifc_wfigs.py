"""NIFC / WFIGS Fire Perimeter Connector.

Queries the WFIGS "Current Interagency Fire Perimeters" ArcGIS feature service
for perimeters intersecting the search box. No API key required.
"""
from __future__ import annotations
import json
from .base import (
    ConnectorContext, http_client, failed, utcnow_iso, point_bbox, haversine_miles,
)
from ..schemas import ConnectorOutput

NAME = "nifc_wfigs"
SOURCE = "NIFC WFIGS Current Interagency Fire Perimeters"
SERVICE = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query"
)
PUBLIC_URL = "https://data-nifc.opendata.arcgis.com/"


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


def _point_in_geometry(lat, lon, geom) -> bool:
    if not geom:
        return False
    gtype = geom.get("type")
    coords = geom.get("coordinates", [])
    polys = coords if gtype == "MultiPolygon" else [coords] if gtype == "Polygon" else []
    for poly in polys:
        if poly and _point_in_ring(lat, lon, poly[0]):
            # outer ring hit; ignore holes for a planning-level flag
            return True
    return False


def _geom_centroid(geom):
    pts = []

    def walk(c):
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
            pts.append(c)
        elif isinstance(c, (list, tuple)):
            for x in c:
                walk(x)
    walk(geom.get("coordinates", []))
    if not pts:
        return None
    return (sum(p[1] for p in pts) / len(pts), sum(p[0] for p in pts) / len(pts))


def run(ctx: ConnectorContext) -> ConnectorOutput:
    radius = float(ctx.settings.get("fire_radius_miles", 30))
    bbox = ctx.bbox or point_bbox(ctx.latitude, ctx.longitude, radius)
    params = {
        "where": "1=1",
        "geometry": json.dumps({
            "xmin": bbox["west"], "ymin": bbox["south"],
            "xmax": bbox["east"], "ymax": bbox["north"],
            "spatialReference": {"wkid": 4326},
        }),
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326, "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "poly_IncidentName,poly_GISAcres,attr_IncidentSize,attr_PercentContained,"
                     "poly_DateCurrent,attr_FireDiscoveryDateTime,attr_IncidentTypeCategory",
        "returnGeometry": "true",
        "geometryPrecision": 4,
        "f": "geojson",
        "resultRecordCount": 25,
    }
    try:
        with http_client() as client:
            r = client.get(SERVICE, params=params)
            r.raise_for_status()
            gj = r.json()
            if "error" in gj:
                return failed(NAME, SOURCE, PUBLIC_URL, json.dumps(gj["error"])[:300])
            perimeters = []
            point_inside = False
            for feat in gj.get("features", []):
                p = feat.get("properties", {}) or {}
                geom = feat.get("geometry")
                inside = _point_in_geometry(ctx.latitude, ctx.longitude, geom)
                point_inside = point_inside or inside
                centroid = _geom_centroid(geom) if geom else None
                dist = (round(haversine_miles(ctx.latitude, ctx.longitude, *centroid), 1)
                        if centroid else None)
                perimeters.append({
                    "name": p.get("poly_IncidentName") or "Unnamed incident",
                    "acres": p.get("poly_GISAcres") or p.get("attr_IncidentSize"),
                    "percent_contained": p.get("attr_PercentContained"),
                    "updated": p.get("poly_DateCurrent"),
                    "type": p.get("attr_IncidentTypeCategory"),
                    "selected_point_inside": inside,
                    "approx_distance_miles": dist,
                    "geometry": geom,
                })
            normalized = {
                "search_bbox": bbox,
                "count": len(perimeters),
                "selected_point_inside_perimeter": point_inside,
                "perimeters": perimeters,
            }
            return ConnectorOutput(
                connector_name=NAME, status="success", source_name=SOURCE,
                source_url=PUBLIC_URL, source_timestamp=utcnow_iso(),
                raw={"feature_count": len(perimeters)}, normalized=normalized,
            )
    except Exception as e:  # noqa: BLE001
        return failed(NAME, SOURCE, PUBLIC_URL, str(e))
