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


from ..schemas import LayerDataResponse
from ..services.layer_data import layer_features


@router.get("/map/layer/{layer_id}", response_model=LayerDataResponse)
def get_layer(layer_id: str, west: float, south: float, east: float, north: float):
    if not (-90 <= south <= 90 and -90 <= north <= 90 and -180 <= west <= 180 and -180 <= east <= 180):
        raise HTTPException(400, "bbox out of range")
    return layer_features(layer_id, {"west": west, "south": south, "east": east, "north": north})
