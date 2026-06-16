"""Route builder endpoints: snap waypoints to trails, and save a built route to
a trip. Saving reuses the GpxRoute storage path so built routes render and drive
condition checks exactly like an uploaded GPX route."""
from __future__ import annotations
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..schemas import RouteSnapRequest, RouteSnapResponse, BuiltRouteSaveRequest, TripOut
from ..security import get_current_user
from ..services import route_builder
from ..services.routing_provider import snap_route
from .trips import _owned_trip, _trip_out

router = APIRouter()


@router.post("/routes/snap", response_model=RouteSnapResponse)
def snap(body: RouteSnapRequest, user: models.User = Depends(get_current_user)):
    waypoints = [(w.lat, w.lon) for w in body.waypoints]
    options = body.options.model_dump() if body.options else {}
    return RouteSnapResponse(**snap_route(waypoints, body.profile, options))


@router.post("/trips/{trip_id}/built-route", response_model=TripOut)
def save_built_route(trip_id: int, body: BuiltRouteSaveRequest,
                     db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    trip = _owned_trip(trip_id, user, db)
    try:
        route_builder.validate_points(body.points)
    except ValueError as e:
        raise HTTPException(400, str(e))

    points = [[p[0], p[1], (p[2] if len(p) > 2 else None)] for p in body.points]
    length = body.length_miles
    if length is None:
        length = route_builder.haversine_length_miles(points)
    if body.bbox and len(body.bbox) >= 4:
        store_bbox = {"west": body.bbox[0], "south": body.bbox[1],
                      "east": body.bbox[2], "north": body.bbox[3]}
    else:
        store_bbox = route_builder.bbox_from_points(points)["store"]
    eles = [p[2] for p in points if p[2] is not None]

    route = models.GpxRoute(
        trip_id=trip_id,
        filename=(body.name or "Built route"),
        points_json=json.dumps(points),
        bbox_json=json.dumps(store_bbox),
        length_miles=length,
        min_elevation_ft=round(min(eles)) if eles else None,
        max_elevation_ft=round(max(eles)) if eles else None,
    )
    db.add(route)
    db.flush()
    trip.gpx_route_id = route.id
    db.commit()
    db.refresh(trip)
    return _trip_out(trip)
