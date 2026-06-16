"""Build a ConnectorContext for wrapping existing connectors from the public
point-context path. Keys come from env (operator-provided); no DB needed."""
from __future__ import annotations
from ..connectors.base import ConnectorContext
from ..services.settings_service import get_api_key

_DEFAULT_SETTINGS = {"fire_radius_miles": 30}


def connector_ctx(lat: float, lon: float, bbox: dict | None = None,
                  keys=("firms", "airnow", "nps"), settings: dict | None = None) -> ConnectorContext:
    api_keys = {k: get_api_key(None, k) for k in keys}
    return ConnectorContext(
        latitude=lat, longitude=lon, start_date="", end_date="",
        bbox=bbox, settings=settings or dict(_DEFAULT_SETTINGS), api_keys=api_keys,
    )
