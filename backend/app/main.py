"""SummitSignal backend entrypoint.

Run with:  uvicorn app.main:app --reload --port 8000
Creates the SQLite schema on startup and seeds four sample trips when the
database is empty.
"""
from __future__ import annotations
import datetime as dt
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401 — registers tables
from .database import Base, engine, SessionLocal
from .routes import trips as trips_routes
from .routes import checks as checks_routes
from .routes import misc as misc_routes
from .agent import scheduler
from .services.settings_service import get_settings

SEED_TRIPS = [
    {"name": "Mount Rainier — DC Route", "location_name": "Mount Rainier, WA",
     "latitude": 46.8523, "longitude": -121.7603, "trip_type": "mountaineering",
     "notes": "Sample trip seeded for testing. Paradise to Camp Muir to summit via "
              "Disappointment Cleaver.",
     "elevation_bands": '{"trailhead_ft": 5400, "mid_ft": 10080, "high_ft": 14410}'},
    {"name": "Longs Peak — Keyhole", "location_name": "Longs Peak, CO",
     "latitude": 40.2549, "longitude": -105.6160, "trip_type": "mountaineering",
     "notes": "Sample trip seeded for testing.",
     "elevation_bands": '{"trailhead_ft": 9405, "mid_ft": 12000, "high_ft": 14259}'},
    {"name": "Yosemite Valley weekend", "location_name": "Yosemite Valley, CA",
     "latitude": 37.7456, "longitude": -119.5936, "trip_type": "backpacking",
     "notes": "Sample trip seeded for testing.", "elevation_bands": None},
    {"name": "Grand Canyon South Rim", "location_name": "Grand Canyon South Rim, AZ",
     "latitude": 36.0544, "longitude": -112.1401, "trip_type": "general",
     "notes": "Sample trip seeded for testing.", "elevation_bands": None},
]


def seed(db):
    if db.query(models.Trip).count() > 0:
        return
    today = dt.date.today()
    start = (today + dt.timedelta(days=7)).isoformat()
    end = (today + dt.timedelta(days=9)).isoformat()
    for t in SEED_TRIPS:
        db.add(models.Trip(start_date=start, end_date=end, **t))
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
        scheduler.start()
        hours = float(get_settings(db).get("schedule_hours", 0) or 0)
        if hours > 0:
            scheduler.set_interval_hours(hours)
    finally:
        db.close()
    yield
    scheduler.shutdown()


app = FastAPI(title="SummitSignal", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "app": "SummitSignal", "time": dt.datetime.now(dt.timezone.utc)}


app.include_router(trips_routes.router)
app.include_router(checks_routes.router)
app.include_router(misc_routes.router)
