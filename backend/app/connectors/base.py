"""Shared connector plumbing.

Every connector module exposes:  run(ctx: ConnectorContext) -> ConnectorOutput
Connectors are isolated: they never touch the database and never raise;
failures come back as status="failed" with an error_message. That keeps the
job runner simple and makes connectors replaceable.
"""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field
from typing import Optional
import httpx

from ..schemas import ConnectorOutput

USER_AGENT = "SummitSignal/0.1 (local trip-planning tool; contact: local-user)"
DEFAULT_TIMEOUT = 20.0


@dataclass
class ConnectorContext:
    """Everything a connector may need, resolved before the job runs."""
    latitude: float
    longitude: float
    start_date: str
    end_date: str
    trip_type: str = "general"
    bbox: Optional[dict] = None            # {"west","south","east","north"} from GPX
    elevation_ft: Optional[float] = None   # filled after usgs_elevation runs
    elevation_bands: Optional[dict] = None
    settings: dict = field(default_factory=dict)
    api_keys: dict = field(default_factory=dict)  # plaintext keys for this run
    shared: dict = field(default_factory=dict)    # cross-connector scratch (e.g. NWS office)


def http_client() -> httpx.Client:
    return httpx.Client(
        timeout=DEFAULT_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        follow_redirects=True,
    )


def failed(name: str, source_name: str, source_url: str, error: str) -> ConnectorOutput:
    return ConnectorOutput(
        connector_name=name, status="failed", source_name=source_name,
        source_url=source_url, error_message=str(error)[:1000],
    )


def skipped(name: str, source_name: str, reason: str) -> ConnectorOutput:
    return ConnectorOutput(
        connector_name=name, status="skipped", source_name=source_name,
        error_message=reason,
    )


def utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def point_bbox(lat: float, lon: float, radius_miles: float) -> dict:
    """Rough bounding box around a point (good enough for fire searches)."""
    import math
    dlat = radius_miles / 69.0
    dlon = radius_miles / (69.0 * max(0.1, math.cos(math.radians(lat))))
    return {"west": lon - dlon, "south": lat - dlat, "east": lon + dlon, "north": lat + dlat}


def haversine_miles(lat1, lon1, lat2, lon2) -> float:
    import math
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
