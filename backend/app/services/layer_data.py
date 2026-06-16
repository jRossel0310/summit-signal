"""Viewport (bbox) -> GeoJSON for hazard map layers. Wraps existing connectors;
keys from env; cached by (layer, rounded bbox). Never raises."""
from __future__ import annotations
import datetime as dt
import time
from collections import OrderedDict
from ..connectors import nasa_firms, nifc_wfigs, avalanche
from ..providers._wrap import connector_ctx
from ..services.settings_service import get_api_key
from ..connectors.base import ConnectorContext

_TTL = {"fires": 300.0, "perimeters": 1800.0, "avalanche": 1800.0, "aqi": 900.0}
_CACHE_MAX = 256
_cache: "OrderedDict[tuple, tuple[float, dict]]" = OrderedDict()


def clear_cache() -> None:
    _cache.clear()


def _bbox_ctx(bbox: dict) -> ConnectorContext:
    cx = (bbox["west"] + bbox["east"]) / 2
    cy = (bbox["south"] + bbox["north"]) / 2
    ctx = connector_ctx(cy, cx, bbox=bbox)
    return ctx


def _fires(bbox):
    if not get_api_key(None, "firms"):
        return "needs_key", []
    out = nasa_firms.run(_bbox_ctx(bbox))
    feats = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [d["longitude"], d["latitude"]]},
        "properties": {"confidence": d.get("confidence"), "acq_date": d.get("acq_date"),
                       "distance_miles": d.get("distance_miles")},
    } for d in (out.normalized or {}).get("detections", [])]
    return "ok", feats


def _perimeters(bbox):
    out = nifc_wfigs.run(_bbox_ctx(bbox))
    feats = [{
        "type": "Feature", "geometry": p.get("geometry"),
        "properties": {"name": p.get("name"), "acres": p.get("acres"),
                       "percent_contained": p.get("percent_contained")},
    } for p in (out.normalized or {}).get("perimeters", []) if p.get("geometry")]
    return "ok", feats


def _avalanche(bbox):
    from ..connectors.base import http_client
    with http_client() as client:
        r = client.get(avalanche.MAP_LAYER)
        r.raise_for_status()
        gj = r.json()
    feats = []
    for feat in gj.get("features", []):
        props = feat.get("properties") or {}
        feats.append({"type": "Feature", "geometry": feat.get("geometry"),
                      "properties": {"name": props.get("name"), "danger": props.get("danger"),
                                     "center": props.get("center")}})
    return "ok", feats


def _aqi(bbox):
    key = get_api_key(None, "airnow")
    if not key:
        return "needs_key", []
    from ..connectors.base import http_client
    now = dt.datetime.now(dt.timezone.utc)
    end = now.strftime("%Y-%m-%dT%H")
    start = (now - dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H")
    params = {
        "startDate": start, "endDate": end,
        "parameters": "PM25", "BBOX": f"{bbox['west']},{bbox['south']},{bbox['east']},{bbox['north']}",
        "dataType": "A", "format": "application/json", "verbose": 1, "API_KEY": key,
    }
    with http_client() as client:
        r = client.get("https://www.airnowapi.org/aq/data/", params=params)
        r.raise_for_status()
        data = r.json()
        rows = data if isinstance(data, list) else []
    feats = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row.get("Longitude"), row.get("Latitude")]},
        "properties": {"aqi": row.get("AQI"), "parameter": row.get("Parameter"),
                       "site": row.get("SiteName")},
    } for row in rows if row.get("Latitude") is not None]
    return "ok", feats


_FETCHERS = {"fires": _fires, "perimeters": _perimeters,
             "avalanche": _avalanche, "aqi": _aqi}


def _key(layer_id, bbox):
    return (layer_id, round(bbox["west"], 2), round(bbox["south"], 2),
            round(bbox["east"], 2), round(bbox["north"], 2))


def layer_features(layer_id: str, bbox: dict) -> dict:
    if layer_id not in _FETCHERS:
        return {"status": "error", "features": []}
    key = _key(layer_id, bbox)
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and (now - hit[0]) < _TTL.get(layer_id, 600.0):
        _cache.move_to_end(key)
        return hit[1]
    try:
        status, feats = _FETCHERS[layer_id](bbox)
        result = {"status": status, "features": feats}
    except Exception as e:  # noqa: BLE001
        result = {"status": "error", "features": [], "message": str(e)[:200]}
    _cache[key] = (now, result)
    _cache.move_to_end(key)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return result
