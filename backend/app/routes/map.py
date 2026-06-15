"""Live point-context route. Read-only; never touches the condition-check
pipeline or the database. Public (no auth), like the map itself."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException

from ..schemas import PointContextResponse
from ..providers.aggregator import point_context

router = APIRouter()


@router.get("/map/point-context", response_model=PointContextResponse)
def get_point_context(lat: float, lon: float, layers: str | None = None):
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(400, "lat/lon out of range")
    layer_ids = [s for s in (layers or "").split(",") if s] or None
    return point_context(lat, lon, layer_ids)
