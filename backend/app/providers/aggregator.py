"""Point-context aggregator: fan out to selected providers, cache by rounded
point, and return a SelectionResult-shaped dict. In-memory TTL+LRU cache so
repeated map clicks do not spam upstreams."""
from __future__ import annotations
import time
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from .base import ProviderContext, ProviderResult, error
from .registry import select_providers

CACHE_TTL_SECONDS = 1800.0    # elevation / place name are ~static
CACHE_MAX = 512
_cache: "OrderedDict[tuple, tuple[float, ProviderResult]]" = OrderedDict()
_lock = threading.Lock()

_STATUS_WIRE = {
    "ok": "ok", "empty": "empty", "error": "error",
    "needs_key": "needs-key", "coming_soon": "coming-soon", "loading": "loading",
}


def clear_cache() -> None:
    _cache.clear()


def _cache_key(provider_id, lat, lon):
    return (provider_id, round(lat, 4), round(lon, 4))


def _cached_fetch(provider, ctx) -> ProviderResult:
    key = _cache_key(provider.id, ctx.latitude, ctx.longitude)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and (now - hit[0]) < CACHE_TTL_SECONDS:
            _cache.move_to_end(key)
            return hit[1]
    try:
        result = provider.fetch(ctx)   # network I/O OUTSIDE the lock
    except Exception as e:  # providers should never raise, but never trust it
        result = error(provider.id, getattr(provider, "title", provider.id), str(e))
    with _lock:
        _cache[key] = (time.monotonic(), result)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)
    return result


def _section_wire(r: ProviderResult) -> dict:
    source = None
    if r.source_name:
        source = {"name": r.source_name, "url": r.source_url, "timestamp": r.source_timestamp}
    return {"layer_id": r.provider_id, "title": r.title,
            "status": _STATUS_WIRE.get(r.status, r.status),
            "data": r.data, "message": r.message, "source": source}


def point_context(lat: float, lon: float, layer_ids=None, settings=None) -> dict:
    ctx = ProviderContext(latitude=lat, longitude=lon, settings=settings or {})
    providers = select_providers(layer_ids)
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(providers)))) as pool:
        results = list(pool.map(lambda p: _cached_fetch(p, ctx), providers))
    place_name = None
    sections = []
    for provider, res in zip(providers, results):
        if provider.id == "placename":
            if res.status == "ok" and res.data:
                place_name = res.data.get("name")
            continue
        sections.append(_section_wire(res))
    return {"lat": lat, "lon": lon, "place_name": place_name, "sections": sections}
