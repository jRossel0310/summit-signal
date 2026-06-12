"""Settings access. Settings live in the app_settings table as JSON-ish strings;
API keys live in api_keys. Environment variables override stored keys:
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
        "nws_weather": True,
        "usgs_elevation": True,
        "elevation_adjusted": True,
        "nasa_firms": True,
        "nifc_wfigs": True,
        "airnow": True,
        "nps_alerts": True,
        "avalanche": True,
        "weather_discussion": True,
    },
    "ollama_enabled": False,
    "ollama_url": "http://localhost:11434",
    "ollama_model": "",
    "schedule_hours": 0.0,
}

ENV_KEY_MAP = {
    "firms": "SUMMIT_SIGNAL_FIRMS_KEY",
    "airnow": "SUMMIT_SIGNAL_AIRNOW_KEY",
    "nps": "SUMMIT_SIGNAL_NPS_KEY",
}


def get_settings(db: Session) -> dict:
    out = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy
    for row in db.query(models.AppSetting).all():
        if row.key in out:
            try:
                out[row.key] = json.loads(row.value)
            except (json.JSONDecodeError, TypeError):
                continue  # unparseable — keep the typed default rather than a raw string
    return out


def update_settings(db: Session, updates: dict) -> dict:
    for key, value in updates.items():
        if key not in DEFAULT_SETTINGS or value is None:
            continue
        if key == "connectors_enabled":
            current = get_settings(db)["connectors_enabled"]
            current.update(value)
            value = current
        row = db.get(models.AppSetting, key)
        if row is None:
            row = models.AppSetting(key=key, value=json.dumps(value))
            db.add(row)
        else:
            row.value = json.dumps(value)
    db.commit()
    return get_settings(db)


def set_api_key(db: Session, name: str, value: str):
    row = db.get(models.ApiKey, name)
    if row is None:
        db.add(models.ApiKey(name=name, value=value))
    else:
        row.value = value
    db.commit()


def get_api_key(db: Session, name: str) -> str:
    env_var = ENV_KEY_MAP.get(name)
    if env_var and os.environ.get(env_var):
        return os.environ[env_var]
    row = db.get(models.ApiKey, name)
    return (row.value or "").strip() if row else ""


def api_keys_present(db: Session) -> dict:
    return {name: bool(get_api_key(db, name)) for name in ENV_KEY_MAP}
