"""Settings routes, location search, and agent control routes."""
from __future__ import annotations
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..schemas import (
    SettingsOut, SettingsUpdate, LocationSearchRequest, LocationSearchResult,
    LocationSearchResponse, ScheduleRequest,
)
from ..services.settings_service import (
    get_settings, update_settings, set_api_key, api_keys_present,
)
from ..connectors.base import http_client
from ..agent import jobs, scheduler, ollama_client

router = APIRouter()

COORD_RE = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


# ---------------- settings ----------------

@router.get("/settings", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db)):
    s = get_settings(db)
    s["api_keys_present"] = api_keys_present(db)
    return SettingsOut(**s)


@router.post("/settings", response_model=SettingsOut)
def write_settings(body: SettingsUpdate, db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    keys = data.pop("api_keys", None)
    if keys:
        for name, value in keys.items():
            if name in ("firms", "airnow", "nps"):
                set_api_key(db, name, value or "")
    s = update_settings(db, data)
    if "schedule_hours" in data and data["schedule_hours"] is not None:
        scheduler.set_interval_hours(float(data["schedule_hours"]))
    s["api_keys_present"] = api_keys_present(db)
    return SettingsOut(**s)


@router.get("/settings/ollama-models")
def ollama_models(db: Session = Depends(get_db)):
    s = get_settings(db)
    url = s.get("ollama_url", "http://localhost:11434")
    available = ollama_client.is_available(url)
    return {"available": available, "models": ollama_client.list_models(url) if available else []}


# ---------------- location search ----------------

@router.post("/search/location", response_model=LocationSearchResponse)
def search_location(body: LocationSearchRequest, db: Session = Depends(get_db)):
    q = body.query.strip()
    if not q:
        raise HTTPException(400, "Empty search query")
    m = COORD_RE.match(q)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return LocationSearchResponse(results=[
                LocationSearchResult(display_name=f"Coordinate {lat:.4f}, {lon:.4f}",
                                     latitude=lat, longitude=lon,
                                     kind="coordinate", source="manual")])
    try:
        with http_client() as client:
            r = client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": q, "format": "jsonv2", "countrycodes": "us", "limit": 6,
                        "addressdetails": 0},
            )
            r.raise_for_status()
            rows = r.json()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Location search failed (Nominatim unreachable): {e}")
    results = []
    for row in rows:
        try:
            results.append(LocationSearchResult(
                display_name=row.get("display_name", q),
                latitude=float(row["lat"]), longitude=float(row["lon"]),
                kind=row.get("type", ""), source="nominatim",
            ))
        except (KeyError, ValueError):
            continue
    for res in results[:1]:
        db.add(models.Location(name=res.display_name, latitude=res.latitude,
                               longitude=res.longitude, kind=res.kind, source=res.source))
    db.commit()
    return LocationSearchResponse(results=results)


# ---------------- agent ----------------

@router.post("/agent/run-all-saved-trips")
def run_all():
    check_ids = jobs.run_all_saved_trips()
    return {"started_condition_checks": check_ids}


@router.post("/agent/schedule")
def set_schedule(body: ScheduleRequest, db: Session = Depends(get_db)):
    update_settings(db, {"schedule_hours": body.hours})
    scheduler.set_interval_hours(body.hours)
    return {"schedule_hours": body.hours, "jobs": scheduler.list_jobs()}


@router.get("/agent/jobs")
def get_jobs():
    return {"jobs": scheduler.list_jobs()}
