"""Settings routes, location search, and agent control routes."""
from __future__ import annotations
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..schemas import (
    SettingsOut, SettingsUpdate, LocationSearchRequest, LocationSearchResult,
    LocationSearchResponse,
)
from ..services.settings_service import (
    get_settings, update_settings, api_keys_present,
)
from ..security import get_current_user
from ..connectors.base import http_client
from ..agent import jobs

router = APIRouter()

COORD_RE = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


# ---------------- settings ----------------

@router.get("/settings", response_model=SettingsOut)
def read_settings(db: Session = Depends(get_db),
                  user: models.User = Depends(get_current_user)):
    s = get_settings(db, user.id)
    s["api_keys_present"] = api_keys_present(db)
    return SettingsOut(**s)


@router.post("/settings", response_model=SettingsOut)
def write_settings(body: SettingsUpdate, db: Session = Depends(get_db),
                   user: models.User = Depends(get_current_user)):
    data = body.model_dump(exclude_unset=True)
    data.pop("api_keys", None)  # API keys are env-only now
    s = update_settings(db, user.id, data)
    s["api_keys_present"] = api_keys_present(db)
    return SettingsOut(**s)


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
def run_all(db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    check_ids = jobs.run_all_saved_trips(user.id)
    return {"started_condition_checks": check_ids}



