"""Trip routes: CRUD, GPX upload, condition-check trigger, print report."""
from __future__ import annotations
import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..schemas import TripCreate, TripUpdate, TripOut, GpxRouteOut, ConditionCheckOut
from ..services import gpx_parser, report_generator
from ..security import get_current_user
from ..agent import jobs

router = APIRouter()


def _owned_trip(trip_id: int, user: models.User, db: Session) -> models.Trip:
    trip = db.get(models.Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(404, "Trip not found")
    return trip


def _trip_out(trip: models.Trip) -> TripOut:
    gpx = None
    if trip.gpx_route:
        r = trip.gpx_route
        gpx = GpxRouteOut(
            id=r.id, filename=r.filename,
            points=json.loads(r.points_json or "[]"),
            bbox=json.loads(r.bbox_json) if r.bbox_json else None,
            length_miles=r.length_miles,
            min_elevation_ft=r.min_elevation_ft, max_elevation_ft=r.max_elevation_ft,
        )
    return TripOut(
        id=trip.id, name=trip.name, location_name=trip.location_name or "",
        latitude=trip.latitude, longitude=trip.longitude,
        start_date=trip.start_date, end_date=trip.end_date,
        trip_type=trip.trip_type, notes=trip.notes or "",
        elevation_bands=json.loads(trip.elevation_bands) if trip.elevation_bands else None,
        gpx_route_id=trip.gpx_route_id, gpx_route=gpx,
        created_at=trip.created_at, updated_at=trip.updated_at,
        last_checked_at=trip.last_checked_at,
        latest_concern_status=trip.latest_concern_status,
    )


@router.post("/trips", response_model=TripOut)
def create_trip(body: TripCreate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    trip = models.Trip(
        user_id=user.id,
        name=body.name, location_name=body.location_name,
        latitude=body.latitude, longitude=body.longitude,
        start_date=body.start_date, end_date=body.end_date,
        trip_type=body.trip_type, notes=body.notes,
        elevation_bands=body.elevation_bands.model_dump_json() if body.elevation_bands else None,
    )
    db.add(trip)
    # also record the location for search history
    db.add(models.Location(name=body.location_name or body.name,
                           latitude=body.latitude, longitude=body.longitude,
                           kind="trip", source="manual"))
    db.commit()
    db.refresh(trip)
    return _trip_out(trip)


@router.get("/trips", response_model=list[TripOut])
def list_trips(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    trips = (db.query(models.Trip).filter(models.Trip.user_id == user.id)
             .order_by(models.Trip.created_at.desc()).all())
    return [_trip_out(t) for t in trips]


@router.get("/trips/{trip_id}", response_model=TripOut)
def get_trip(trip_id: int, db: Session = Depends(get_db),
             user: models.User = Depends(get_current_user)):
    return _trip_out(_owned_trip(trip_id, user, db))


@router.patch("/trips/{trip_id}", response_model=TripOut)
def update_trip(trip_id: int, body: TripUpdate, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    trip = _owned_trip(trip_id, user, db)
    data = body.model_dump(exclude_unset=True)
    if "elevation_bands" in data and data["elevation_bands"] is not None:
        data["elevation_bands"] = json.dumps(data["elevation_bands"])
    for k, v in data.items():
        setattr(trip, k, v)  # exclude_unset already filtered to provided fields
    db.commit()
    db.refresh(trip)
    return _trip_out(trip)


@router.delete("/trips/{trip_id}")
def delete_trip(trip_id: int, db: Session = Depends(get_db),
                user: models.User = Depends(get_current_user)):
    trip = _owned_trip(trip_id, user, db)
    db.delete(trip)  # ORM cascade removes checks, connector results, flags, summaries, reports
    db.commit()
    return {"deleted": trip_id}


@router.post("/trips/{trip_id}/upload-gpx", response_model=TripOut)
async def upload_gpx(trip_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    trip = _owned_trip(trip_id, user, db)
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(413, "GPX file larger than 10 MB")
    try:
        parsed = gpx_parser.parse_gpx(content)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Could not parse GPX file: {e}")
    route = models.GpxRoute(
        trip_id=trip_id, filename=file.filename or "route.gpx",
        points_json=json.dumps(parsed["points"]),
        bbox_json=json.dumps(parsed["bbox"]),
        length_miles=parsed["length_miles"],
        min_elevation_ft=parsed["min_elevation_ft"],
        max_elevation_ft=parsed["max_elevation_ft"],
    )
    db.add(route)
    db.flush()
    trip.gpx_route_id = route.id
    db.commit()
    db.refresh(trip)
    return _trip_out(trip)


@router.post("/trips/{trip_id}/run-condition-check", response_model=ConditionCheckOut)
def run_condition_check(trip_id: int, db: Session = Depends(get_db),
                        user: models.User = Depends(get_current_user)):
    _owned_trip(trip_id, user, db)
    check_id = jobs.start_condition_check(trip_id)
    check = db.get(models.ConditionCheck, check_id)
    return ConditionCheckOut(
        id=check.id, trip_id=check.trip_id, started_at=check.started_at,
        completed_at=check.completed_at, status=check.status,
        overall_concern_status=check.overall_concern_status,
        data_completeness_score=check.data_completeness_score,
        summary_text=None,
    )


@router.get("/trips/{trip_id}/checks")
def list_trip_checks(trip_id: int, db: Session = Depends(get_db),
                     user: models.User = Depends(get_current_user)):
    _owned_trip(trip_id, user, db)
    checks = (db.query(models.ConditionCheck).filter_by(trip_id=trip_id)
              .order_by(models.ConditionCheck.started_at.desc()).all())
    return [{"id": c.id, "started_at": c.started_at, "completed_at": c.completed_at,
             "status": c.status, "overall_concern_status": c.overall_concern_status,
             "data_completeness_score": c.data_completeness_score} for c in checks]


@router.get("/trips/{trip_id}/print-report", response_class=HTMLResponse)
def print_report(trip_id: int, check_id: int | None = None, db: Session = Depends(get_db),
                 user: models.User = Depends(get_current_user)):
    trip = _owned_trip(trip_id, user, db)
    if check_id:
        check = db.get(models.ConditionCheck, check_id)
        if check is None or check.trip_id != trip.id:
            raise HTTPException(404, "Condition check not found")
    else:
        check = (db.query(models.ConditionCheck)
                 .filter_by(trip_id=trip_id, status="complete")
                 .order_by(models.ConditionCheck.completed_at.desc()).first())
    html = report_generator.generate_report_html(trip, check)
    db.add(models.SavedReport(trip_id=trip_id,
                              condition_check_id=check.id if check else None, html=html))
    db.commit()
    return HTMLResponse(html)
