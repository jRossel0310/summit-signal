"""Settings access. Settings live in the app_settings table as JSON-ish strings,
scoped per user via a composite (user_id, key) primary key. API keys are not
stored in the database; they come from environment variables only:
SUMMIT_SIGNAL_FIRMS_KEY, SUMMIT_SIGNAL_AIRNOW_KEY, SUMMIT_SIGNAL_NPS_KEY.
"""
import json
import os
from sqlalchemy.orm import Session
from .. import models

DEFAULT_SETTINGS = {
    "fire_radius_miles": 30.0,
    "aqi_moderate_threshold": 101,
    "aqi_major_threshold": 151,
    "wind_gust_moderate_mph": 30.0,
    "wind_gust_major_mph": 50.0,
    "precip_prob_moderate": 60.0,
    "cold_low_f": 10.0,
    "stale_hours": 24.0,
    "connectors_enabled": {
        "nws_weather": True, "usgs_elevation": True, "elevation_adjusted": True,
        "nasa_firms": True, "nifc_wfigs": True, "airnow": True,
        "nps_alerts": True, "avalanche": True, "weather_discussion": True,
    },
}

ENV_KEY_MAP = {
    "firms": "SUMMIT_SIGNAL_FIRMS_KEY",
    "airnow": "SUMMIT_SIGNAL_AIRNOW_KEY",
    "nps": "SUMMIT_SIGNAL_NPS_KEY",
    "ors": "SUMMIT_SIGNAL_ORS_KEY",
}


def get_settings(db: Session, user_id: int) -> dict:
    out = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy
    rows = db.query(models.AppSetting).filter(models.AppSetting.user_id == user_id).all()
    for row in rows:
        if row.key in out:
            try:
                out[row.key] = json.loads(row.value)
            except (json.JSONDecodeError, TypeError):
                continue  # unparseable; keep the typed default rather than a raw string
    return out


def update_settings(db: Session, user_id: int, updates: dict) -> dict:
    for key, value in updates.items():
        if key not in DEFAULT_SETTINGS or value is None:
            continue
        if key == "connectors_enabled":
            current = get_settings(db, user_id)["connectors_enabled"]
            current.update(value)
            value = current
        row = db.get(models.AppSetting, {"user_id": user_id, "key": key})
        if row is None:
            db.add(models.AppSetting(user_id=user_id, key=key, value=json.dumps(value)))
        else:
            row.value = json.dumps(value)
    db.commit()
    return get_settings(db, user_id)


def get_api_key(db, name: str) -> str:
    """API keys come from environment variables only (operator-provided)."""
    env_var = ENV_KEY_MAP.get(name)
    return os.environ.get(env_var, "").strip() if env_var else ""


def api_keys_present(db: Session) -> dict:
    return {name: bool(get_api_key(db, name)) for name in ENV_KEY_MAP}
