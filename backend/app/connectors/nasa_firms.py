"""NASA FIRMS Active Fire Connector.

Fetches recent VIIRS active-fire detections within the route bounding box (or a
radius box around the selected point). Requires a free FIRMS MAP_KEY; the
connector degrades to a clear "API key needed" state when missing.
"""
from __future__ import annotations
import csv
import io
from .base import (
    ConnectorContext, http_client, failed, skipped, utcnow_iso,
    point_bbox, haversine_miles,
)
from ..schemas import ConnectorOutput

NAME = "nasa_firms"
SOURCE = "NASA FIRMS (VIIRS active fire detections)"
DAYS = 3
SENSOR = "VIIRS_SNPP_NRT"


def run(ctx: ConnectorContext) -> ConnectorOutput:
    key = ctx.api_keys.get("firms", "")
    if not key:
        return skipped(
            NAME, SOURCE,
            "API key needed. Get a free FIRMS map key at firms.modaps.eosdis.nasa.gov "
            "and add it in Settings.",
        )
    radius = float(ctx.settings.get("fire_radius_miles", 30))
    bbox = ctx.bbox or point_bbox(ctx.latitude, ctx.longitude, radius)
    # Pad GPX bbox by the search radius too
    if ctx.bbox:
        pad = point_bbox(ctx.latitude, ctx.longitude, radius)
        bbox = {
            "west": min(bbox["west"], ctx.longitude) - (pad["east"] - ctx.longitude),
            "south": min(bbox["south"], ctx.latitude) - (pad["north"] - ctx.latitude),
            "east": max(bbox["east"], ctx.longitude) + (pad["east"] - ctx.longitude),
            "north": max(bbox["north"], ctx.latitude) + (pad["north"] - ctx.latitude),
        }
    area = f"{bbox['west']:.4f},{bbox['south']:.4f},{bbox['east']:.4f},{bbox['north']:.4f}"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{SENSOR}/{area}/{DAYS}"
    public_url = "https://firms.modaps.eosdis.nasa.gov/map/"
    try:
        with http_client() as client:
            r = client.get(url)
            r.raise_for_status()
            text = r.text.strip()
            if text.lower().startswith("invalid"):
                return failed(NAME, SOURCE, public_url, f"FIRMS rejected the request: {text[:200]}")
            detections = []
            if text and "latitude" in text.splitlines()[0]:
                reader = csv.DictReader(io.StringIO(text))
                for row in reader:
                    try:
                        lat = float(row["latitude"]); lon = float(row["longitude"])
                    except (KeyError, ValueError):
                        continue
                    detections.append({
                        "latitude": lat,
                        "longitude": lon,
                        "confidence": row.get("confidence", ""),
                        "acq_date": row.get("acq_date", ""),
                        "acq_time": row.get("acq_time", ""),
                        "frp": row.get("frp", ""),
                        "distance_miles": round(
                            haversine_miles(ctx.latitude, ctx.longitude, lat, lon), 1),
                    })
            detections.sort(key=lambda d: d["distance_miles"])
            nearest = detections[0]["distance_miles"] if detections else None
            normalized = {
                "search_bbox": bbox,
                "search_days": DAYS,
                "sensor": SENSOR,
                "count": len(detections),
                "nearest_miles": nearest,
                "detections": detections[:200],
            }
            return ConnectorOutput(
                connector_name=NAME, status="success", source_name=SOURCE,
                source_url=public_url, source_timestamp=utcnow_iso(),
                raw={"row_count": len(detections)}, normalized=normalized,
            )
    except Exception as e:  # noqa: BLE001
        return failed(NAME, SOURCE, public_url, str(e))
