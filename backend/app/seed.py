"""Sample trips seeded into each new account at signup."""
from __future__ import annotations
import datetime as dt

from . import models

SEED_TRIPS = [
    {"name": "Mount Rainier, DC Route", "location_name": "Mount Rainier, WA",
     "latitude": 46.8523, "longitude": -121.7603, "trip_type": "mountaineering",
     "notes": "Sample trip. Paradise to Camp Muir to summit via Disappointment Cleaver.",
     "elevation_bands": '{"trailhead_ft": 5400, "mid_ft": 10080, "high_ft": 14410}'},
    {"name": "Longs Peak, Keyhole", "location_name": "Longs Peak, CO",
     "latitude": 40.2549, "longitude": -105.6160, "trip_type": "mountaineering",
     "notes": "Sample trip.",
     "elevation_bands": '{"trailhead_ft": 9405, "mid_ft": 12000, "high_ft": 14259}'},
    {"name": "Yosemite Valley weekend", "location_name": "Yosemite Valley, CA",
     "latitude": 37.7456, "longitude": -119.5936, "trip_type": "backpacking",
     "notes": "Sample trip.", "elevation_bands": None},
    {"name": "Grand Canyon South Rim", "location_name": "Grand Canyon South Rim, AZ",
     "latitude": 36.0544, "longitude": -112.1401, "trip_type": "general",
     "notes": "Sample trip.", "elevation_bands": None},
]


def seed_for_user(db, user_id: int) -> None:
    today = dt.date.today()
    start = (today + dt.timedelta(days=7)).isoformat()
    end = (today + dt.timedelta(days=9)).isoformat()
    for t in SEED_TRIPS:
        db.add(models.Trip(user_id=user_id, start_date=start, end_date=end, **t))
    db.commit()
