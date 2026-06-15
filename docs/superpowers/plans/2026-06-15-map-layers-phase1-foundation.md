# Map Layers — Phase 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an extensible map-layer system (frontend layer registry + backend data-provider interface + a live point-context endpoint), ship five basemaps via a hybrid free/MapTiler adapter, add a floating Layers control and a live "This point" dashboard, and migrate today's overlays into the new system — with zero regression to the condition-check flow.

**Architecture:** Frontend owns a typed layer registry (render/UI concerns); backend owns a provider/adapter interface for data layers plus a `GET /map/point-context` aggregator with caching. Providers mirror the existing connector envelope (isolated, never raise). Map click triggers the existing trip-point set **and** a new read-only point-context fetch.

**Tech Stack:** Backend — FastAPI, httpx, pytest (offline). Frontend — Vite + React + TypeScript + MapLibre GL; no test runner (correctness via `tsc -b` + manual verification).

**Spec:** `docs/superpowers/specs/2026-06-15-map-layers-phase1-foundation-design.md`

---

## Conventions for this plan

- **Backend tests** run from the `backend/` directory: `cd backend && python -m pytest tests/<file> -q`. `tests/conftest.py` already isolates the DB and network; new provider tests monkeypatch `http_client` exactly like `tests/test_connectors.py`.
- **Frontend "verify"** = `cd frontend && npx tsc -b` must pass (type check, no emit), plus the stated manual check. Commit only after both pass.
- **Wire format is snake_case** (frontend types mirror backend fields, per `frontend/src/types.ts`). New TS types use `place_name`, `layer_id`, etc.
- Commit after every task. Branch is `feat/map-layers-phase1` (already created).

---

## File Structure

**Backend (new)**
- `backend/app/providers/__init__.py` — package marker.
- `backend/app/providers/base.py` — `ProviderContext`, `ProviderResult`, `Provider` protocol, result factories.
- `backend/app/providers/elevation.py` — `ElevationProvider` (USGS EPQS + Open-Meteo fallback).
- `backend/app/providers/placename.py` — `PlaceNameProvider` (Nominatim reverse geocode).
- `backend/app/providers/stubs.py` — coming-soon stub providers.
- `backend/app/providers/registry.py` — `PROVIDERS` map + `select_providers()`.
- `backend/app/providers/aggregator.py` — `point_context()` + TTL/LRU cache.
- `backend/app/routes/map.py` — `GET /map/point-context`.
- `backend/tests/test_providers.py`, `backend/tests/test_point_context.py`.

**Backend (modified)**
- `backend/app/schemas.py` — add `PointSectionOut`, `PointContextResponse`.
- `backend/app/main.py` — include the map router.

**Frontend (new)**
- `frontend/src/layers/types.ts` — layer + selection types.
- `frontend/src/layers/basemaps.ts` — hybrid basemap adapter.
- `frontend/src/layers/registry.ts` — layer descriptors.
- `frontend/src/layers/layerState.ts` — state seeding + updates.
- `frontend/src/components/Legend.tsx` — legend renderer.
- `frontend/src/components/LayersControl.tsx` — floating layers panel.
- `frontend/src/components/PointDashboard.tsx` — "This point" dashboard.

**Frontend (modified)**
- `frontend/src/lib/api.ts` — add `pointContext()`.
- `frontend/src/components/MapView.tsx` — render from registry/state.
- `frontend/src/App.tsx` — `LayerStateMap`, point-inspect flow, mount control + dashboard.
- `frontend/src/components/PlanPanel.tsx` — drop the map-layers block.
- `frontend/src/index.css` (or the project's stylesheet) — styles for the new components.
- `README.md`, `.env.example` — document `VITE_MAPTILER_KEY`.

---

## Task 1: Provider base types + result factories

**Files:**
- Create: `backend/app/providers/__init__.py`
- Create: `backend/app/providers/base.py`
- Test: `backend/tests/test_providers.py`

- [ ] **Step 1: Create the package marker**

Create `backend/app/providers/__init__.py` (empty file):

```python
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_providers.py`:

```python
"""Provider unit tests: result factories, each provider, registry, aggregator.
All offline — http_client is monkeypatched per module, exactly like
tests/test_connectors.py."""
from app.providers import base
from app.providers.base import ProviderContext


def test_result_factories_set_status():
    assert base.ok("x", "X", {"v": 1}).status == "ok"
    assert base.empty("x", "X", "none").status == "empty"
    nk = base.needs_key("x", "X", "FOO_KEY")
    assert nk.status == "needs_key" and "FOO_KEY" in nk.message
    assert base.error("x", "X", "boom").status == "error"
    assert base.coming_soon("x", "X", 2).status == "coming_soon"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_providers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.providers.base'`

- [ ] **Step 4: Write the implementation**

Create `backend/app/providers/base.py`:

```python
"""Map point-context providers: shared types + result factories.

A Provider answers "what is true at this lat/lon for one layer?" Providers are
isolated like connectors: they never touch the DB and never raise; failures come
back as status="error". Status values map 1:1 onto the frontend SectionStatus
(snake_case here -> kebab-case at the route boundary)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class ProviderContext:
    latitude: float
    longitude: float
    bbox: Optional[dict] = None          # reserved for future route-based analysis
    settings: dict = field(default_factory=dict)
    shared: dict = field(default_factory=dict)


@dataclass
class ProviderResult:
    provider_id: str
    status: str                          # ok | empty | needs_key | error | coming_soon
    title: str
    data: Optional[dict] = None
    message: Optional[str] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    source_timestamp: Optional[str] = None


class Provider(Protocol):
    id: str
    title: str
    requires_key: Optional[str]
    always_on: bool
    def fetch(self, ctx: ProviderContext) -> ProviderResult: ...


def ok(pid, title, data, source_name=None, source_url=None, source_timestamp=None):
    return ProviderResult(pid, "ok", title, data=data, source_name=source_name,
                          source_url=source_url, source_timestamp=source_timestamp)


def empty(pid, title, message):
    return ProviderResult(pid, "empty", title, message=message)


def needs_key(pid, title, env_var):
    return ProviderResult(pid, "needs_key", title,
                          message=f"Set {env_var} on the server to enable this layer.")


def error(pid, title, message):
    return ProviderResult(pid, "error", title, message=str(message)[:500])


def coming_soon(pid, title, phase):
    return ProviderResult(pid, "coming_soon", title, message=f"Arrives in Phase {phase}.")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_providers.py -q`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add backend/app/providers/__init__.py backend/app/providers/base.py backend/tests/test_providers.py
git commit -m "feat(providers): point-context provider base types + result factories"
```

---

## Task 2: ElevationProvider

**Files:**
- Create: `backend/app/providers/elevation.py`
- Test: `backend/tests/test_providers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_providers.py`:

```python
from app.providers import elevation as elevation_mod


class _Resp:
    def __init__(self, payload):
        self._p = payload
    def raise_for_status(self):
        return None
    def json(self):
        return self._p


class _ElevClient:
    """EPQS returns a value unless fail_epqs; Open-Meteo returns om_payload."""
    def __init__(self, epqs_payload=None, fail_epqs=False, om_payload=None):
        self.epqs_payload = epqs_payload
        self.fail_epqs = fail_epqs
        self.om_payload = om_payload
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def get(self, url, params=None):
        if "epqs" in url:
            if self.fail_epqs:
                raise RuntimeError("EPQS down")
            return _Resp(self.epqs_payload)
        return _Resp(self.om_payload or {"elevation": []})


def test_elevation_ok(monkeypatch):
    monkeypatch.setattr(elevation_mod, "http_client",
                        lambda: _ElevClient(epqs_payload={"value": 3186.0}))
    out = elevation_mod.ElevationProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert out.data["elevation_ft"] == round(3186.0 * 3.28084)
    assert "USGS" in out.source_name


def test_elevation_uses_fallback(monkeypatch):
    monkeypatch.setattr(elevation_mod, "http_client",
                        lambda: _ElevClient(fail_epqs=True, om_payload={"elevation": [1000.0]}))
    out = elevation_mod.ElevationProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "ok"
    assert "Open-Meteo" in out.source_name


def test_elevation_never_raises(monkeypatch):
    class _Boom:
        def __enter__(self):
            raise RuntimeError("network gone")
        def __exit__(self, *a):
            return False
    monkeypatch.setattr(elevation_mod, "http_client", lambda: _Boom())
    out = elevation_mod.ElevationProvider().fetch(ProviderContext(40.0, -105.0))
    assert out.status == "error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_providers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.providers.elevation'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/providers/elevation.py`:

```python
"""ElevationProvider: USGS EPQS point elevation with Open-Meteo fallback.
Always-on base context for the point dashboard. Never raises."""
from __future__ import annotations
from ..connectors.base import http_client, utcnow_iso
from .base import ProviderContext, ProviderResult, ok, error

EPQS_URL = "https://epqs.nationalmap.gov/v1/json"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/elevation"


class ElevationProvider:
    id = "elevation"
    title = "Elevation"
    requires_key = None
    always_on = True

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        source_name = "USGS Elevation Point Query Service"
        source_url = EPQS_URL
        try:
            with http_client() as client:
                meters = None
                try:
                    r = client.get(EPQS_URL, params={
                        "x": ctx.longitude, "y": ctx.latitude, "units": "Meters",
                        "wkid": 4326, "includeDate": "false"})
                    r.raise_for_status()
                    value = r.json().get("value")
                    meters = float(value) if value not in (None, "None") else None
                except Exception:  # noqa: BLE001
                    meters = None

                if meters is None:
                    source_name = "Open-Meteo elevation (fallback; USGS EPQS unavailable)"
                    source_url = OPEN_METEO_URL
                    fb = client.get(OPEN_METEO_URL, params={
                        "latitude": ctx.latitude, "longitude": ctx.longitude})
                    fb.raise_for_status()
                    elevs = fb.json().get("elevation") or []
                    if elevs:
                        meters = float(elevs[0])

                if meters is None:
                    return error(self.id, self.title, "No elevation value returned")

                feet = meters * 3.28084
                return ok(self.id, self.title,
                          data={"elevation_ft": round(feet), "elevation_m": round(meters, 1)},
                          source_name=source_name, source_url=source_url,
                          source_timestamp=utcnow_iso())
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_providers.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/elevation.py backend/tests/test_providers.py
git commit -m "feat(providers): ElevationProvider (USGS EPQS + Open-Meteo fallback)"
```

---

## Task 3: PlaceNameProvider

**Files:**
- Create: `backend/app/providers/placename.py`
- Test: `backend/tests/test_providers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_providers.py`:

```python
from app.providers import placename as placename_mod


def test_placename_ok(monkeypatch):
    class _C:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def get(self, url, params=None):
            return _Resp({"display_name": "Near Pingora, WY"})
    monkeypatch.setattr(placename_mod, "http_client", lambda: _C())
    out = placename_mod.PlaceNameProvider().fetch(ProviderContext(42.0, -109.0))
    assert out.status == "ok" and "Pingora" in out.data["name"]


def test_placename_failure_is_empty(monkeypatch):
    class _C:
        def __enter__(self):
            raise RuntimeError("down")
        def __exit__(self, *a):
            return False
    monkeypatch.setattr(placename_mod, "http_client", lambda: _C())
    out = placename_mod.PlaceNameProvider().fetch(ProviderContext(42.0, -109.0))
    assert out.status == "empty"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_providers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.providers.placename'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/providers/placename.py`:

```python
"""PlaceNameProvider: best-effort reverse geocode via Nominatim. Always-on.
On failure returns empty (dashboard shows coordinates only). Never raises."""
from __future__ import annotations
from ..connectors.base import http_client
from .base import ProviderContext, ProviderResult, ok, empty

NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"


class PlaceNameProvider:
    id = "placename"
    title = "Place"
    requires_key = None
    always_on = True

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        try:
            with http_client() as client:
                r = client.get(NOMINATIM_REVERSE, params={
                    "lat": ctx.latitude, "lon": ctx.longitude,
                    "format": "jsonv2", "zoom": 12, "addressdetails": 0})
                r.raise_for_status()
                name = (r.json() or {}).get("display_name")
                if name:
                    return ok(self.id, self.title, data={"name": name},
                              source_name="Nominatim (OpenStreetMap)",
                              source_url="https://nominatim.openstreetmap.org/")
                return empty(self.id, self.title, "No place name found")
        except Exception:  # noqa: BLE001
            return empty(self.id, self.title, "Reverse geocode unavailable")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_providers.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/placename.py backend/tests/test_providers.py
git commit -m "feat(providers): PlaceNameProvider (Nominatim reverse geocode, best-effort)"
```

---

## Task 4: Coming-soon stub providers

**Files:**
- Create: `backend/app/providers/stubs.py`
- Test: `backend/tests/test_providers.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_providers.py`:

```python
from app.providers import stubs


def test_stub_is_coming_soon():
    out = stubs.SlopeAspectStub.fetch(ProviderContext(40.0, -105.0))
    assert out.status == "coming_soon"
    assert out.provider_id == "slope_aspect"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_providers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.providers.stubs'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/providers/stubs.py`:

```python
"""Coming-soon stub providers. Each returns a coming_soon result so the UI and
architecture are real before the data source is wired.

TODO(phase-2): replace SlopeAspectStub with a real DEM-derived provider.
TODO(phase-3): replace WeatherStub with a real nearby-station provider."""
from __future__ import annotations
from .base import ProviderContext, ProviderResult, coming_soon


class _ComingSoon:
    requires_key = None
    always_on = False

    def __init__(self, pid: str, title: str, phase: int):
        self.id = pid
        self.title = title
        self._phase = phase

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        return coming_soon(self.id, self.title, self._phase)


SlopeAspectStub = _ComingSoon("slope_aspect", "Slope & aspect", 2)
WeatherStub = _ComingSoon("weather", "Current weather", 3)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_providers.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/stubs.py backend/tests/test_providers.py
git commit -m "feat(providers): coming-soon stub providers (slope/aspect, weather)"
```

---

## Task 5: Provider registry + selection

**Files:**
- Create: `backend/app/providers/registry.py`
- Test: `backend/tests/test_providers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_providers.py`:

```python
from app.providers import registry


def test_select_includes_always_on_by_default():
    ids = [p.id for p in registry.select_providers(None)]
    assert "elevation" in ids and "placename" in ids
    assert "slope_aspect" not in ids   # toggle-gated, not requested


def test_select_includes_requested():
    ids = [p.id for p in registry.select_providers(["slope_aspect"])]
    assert "slope_aspect" in ids and "elevation" in ids


def test_unknown_id_ignored():
    ids = [p.id for p in registry.select_providers(["nope"])]
    assert "nope" not in ids and "elevation" in ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_providers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.providers.registry'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/providers/registry.py`:

```python
"""Provider registry + selection. PROVIDERS maps provider_id -> instance.
select_providers() returns the always-on base providers plus any requested
toggle-gated providers, de-duplicated and in a stable order."""
from __future__ import annotations
from .base import Provider
from .elevation import ElevationProvider
from .placename import PlaceNameProvider
from . import stubs

_ALL: list[Provider] = [
    PlaceNameProvider(),
    ElevationProvider(),
    stubs.SlopeAspectStub,
    stubs.WeatherStub,
]
PROVIDERS: dict[str, Provider] = {p.id: p for p in _ALL}


def select_providers(layer_ids: list[str] | None) -> list[Provider]:
    requested = set(layer_ids or [])
    return [p for p in _ALL if p.always_on or p.id in requested]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_providers.py -q`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/registry.py backend/tests/test_providers.py
git commit -m "feat(providers): provider registry + always-on/requested selection"
```

---

## Task 6: Point-context aggregator + cache

**Files:**
- Create: `backend/app/providers/aggregator.py`
- Test: `backend/tests/test_providers.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_providers.py`:

```python
from app.providers import aggregator
from app.providers.base import ok as _ok, coming_soon as _coming_soon


def test_point_context_hoists_placename_and_lists_sections(monkeypatch):
    aggregator.clear_cache()

    class _Place:
        id = "placename"; title = "Place"; requires_key = None; always_on = True
        def fetch(self, ctx):
            return _ok(self.id, self.title, {"name": "Near Pingora, WY"})

    class _Elev:
        id = "elevation"; title = "Elevation"; requires_key = None; always_on = True
        def fetch(self, ctx):
            return _ok(self.id, self.title, {"elevation_ft": 10450})

    monkeypatch.setattr(aggregator, "select_providers", lambda ids: [_Place(), _Elev()])
    out = aggregator.point_context(40.0, -105.0)
    assert out["place_name"] == "Near Pingora, WY"
    ids = [s["layer_id"] for s in out["sections"]]
    assert ids == ["elevation"]   # placename hoisted to top level, not a section


def test_cache_prevents_refetch(monkeypatch):
    aggregator.clear_cache()

    class _Counter:
        id = "elevation"; title = "Elevation"; requires_key = None; always_on = True
        calls = 0
        def fetch(self, ctx):
            type(self).calls += 1
            return _ok(self.id, self.title, {"elevation_ft": 1000})

    counter = _Counter()
    monkeypatch.setattr(aggregator, "select_providers", lambda ids: [counter])
    aggregator.point_context(40.0, -105.0)
    aggregator.point_context(40.0, -105.0)
    assert _Counter.calls == 1   # second call served from cache


def test_status_mapped_to_kebab_wire(monkeypatch):
    aggregator.clear_cache()

    class _W:
        id = "weather"; title = "Current weather"; requires_key = None; always_on = False
        def fetch(self, ctx):
            return _coming_soon(self.id, self.title, 3)

    monkeypatch.setattr(aggregator, "select_providers", lambda ids: [_W()])
    out = aggregator.point_context(40.0, -105.0, ["weather"])
    assert out["sections"][0]["status"] == "coming-soon"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_providers.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.providers.aggregator'`

- [ ] **Step 3: Write the implementation**

Create `backend/app/providers/aggregator.py`:

```python
"""Point-context aggregator: fan out to selected providers, cache by rounded
point, and return a SelectionResult-shaped dict. In-memory TTL+LRU cache so
repeated map clicks do not spam upstreams."""
from __future__ import annotations
import time
from collections import OrderedDict
from .base import ProviderContext, ProviderResult, error
from .registry import select_providers

CACHE_TTL_SECONDS = 1800.0    # elevation / place name are ~static
CACHE_MAX = 512
_cache: "OrderedDict[tuple, tuple[float, ProviderResult]]" = OrderedDict()

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
    hit = _cache.get(key)
    if hit and (now - hit[0]) < CACHE_TTL_SECONDS:
        _cache.move_to_end(key)
        return hit[1]
    try:
        result = provider.fetch(ctx)
    except Exception as e:  # providers should never raise, but never trust it
        result = error(provider.id, getattr(provider, "title", provider.id), str(e))
    _cache[key] = (now, result)
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
    place_name = None
    sections = []
    for provider in select_providers(layer_ids):
        res = _cached_fetch(provider, ctx)
        if provider.id == "placename":
            if res.status == "ok" and res.data:
                place_name = res.data.get("name")
            continue   # surfaced at the top level, not as a section
        sections.append(_section_wire(res))
    return {"lat": lat, "lon": lon, "place_name": place_name, "sections": sections}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_providers.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/aggregator.py backend/tests/test_providers.py
git commit -m "feat(providers): point-context aggregator with TTL/LRU cache + wire mapping"
```

---

## Task 7: Point-context route + schemas + wire into app

**Files:**
- Modify: `backend/app/schemas.py` (append schemas)
- Create: `backend/app/routes/map.py`
- Modify: `backend/app/main.py:19,55`
- Test: `backend/tests/test_point_context.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_point_context.py`:

```python
"""Route tests for GET /map/point-context. Offline: both network providers are
monkeypatched. Public endpoint (no auth)."""
import os
import tempfile

os.environ.setdefault("SUMMIT_SIGNAL_DB", os.path.join(tempfile.mkdtemp(), "pc.db"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import elevation as elevation_mod  # noqa: E402
from app.providers import placename as placename_mod  # noqa: E402
from app.providers import aggregator  # noqa: E402

_cm = TestClient(app)
client = _cm.__enter__()


def teardown_module(_m):
    _cm.__exit__(None, None, None)


class _Resp:
    def __init__(self, p):
        self._p = p
    def raise_for_status(self):
        return None
    def json(self):
        return self._p


class _FakeClient:
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def get(self, url, params=None):
        if "epqs" in url:
            return _Resp({"value": 3186.0})
        if "reverse" in url:
            return _Resp({"display_name": "Near Pingora, WY"})
        return _Resp({})


def _patch(monkeypatch):
    aggregator.clear_cache()
    monkeypatch.setattr(elevation_mod, "http_client", lambda: _FakeClient())
    monkeypatch.setattr(placename_mod, "http_client", lambda: _FakeClient())


def test_point_context_returns_sections(monkeypatch):
    _patch(monkeypatch)
    r = client.get("/map/point-context", params={"lat": 40.0, "lon": -105.0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["place_name"] == "Near Pingora, WY"
    elev = next(s for s in body["sections"] if s["layer_id"] == "elevation")
    assert elev["status"] == "ok"
    assert elev["data"]["elevation_ft"] == round(3186.0 * 3.28084)


def test_point_context_no_auth_required(monkeypatch):
    _patch(monkeypatch)
    r = client.get("/map/point-context", params={"lat": 44.0, "lon": -110.0})
    assert r.status_code == 200   # public, like the map


def test_point_context_rejects_bad_coords():
    r = client.get("/map/point-context", params={"lat": 999, "lon": -105.0})
    assert r.status_code == 400


def test_point_context_includes_coming_soon(monkeypatch):
    _patch(monkeypatch)
    r = client.get("/map/point-context",
                   params={"lat": 40.0, "lon": -105.0, "layers": "weather"})
    statuses = {s["layer_id"]: s["status"] for s in r.json()["sections"]}
    assert statuses.get("weather") == "coming-soon"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_point_context.py -q`
Expected: FAIL (404 on `/map/point-context`, so the assertions fail)

- [ ] **Step 3: Add the response schemas**

Append to `backend/app/schemas.py` (end of file):

```python
# ---------- Map point-context ----------

class PointSectionOut(BaseModel):
    layer_id: str
    title: str
    status: str
    data: Optional[dict] = None
    message: Optional[str] = None
    source: Optional[dict] = None


class PointContextResponse(BaseModel):
    lat: float
    lon: float
    place_name: Optional[str] = None
    sections: list[PointSectionOut] = Field(default_factory=list)
```

- [ ] **Step 4: Create the route**

Create `backend/app/routes/map.py`:

```python
"""Live point-context route. Read-only; never touches the condition-check
pipeline or the database. Public (no auth), like the map itself."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException

from ..schemas import PointContextResponse
from ..providers.aggregator import point_context

router = APIRouter()


@router.get("/map/point-context", response_model=PointContextResponse)
def get_point_context(lat: float, lon: float, layers: str | None = None):
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise HTTPException(400, "lat/lon out of range")
    layer_ids = [s for s in (layers or "").split(",") if s] or None
    return point_context(lat, lon, layer_ids)
```

- [ ] **Step 5: Wire the router into the app**

In `backend/app/main.py`, add the import alongside the other route imports (after line 19 `from .routes import misc as misc_routes`):

```python
from .routes import map as map_routes
```

And register it alongside the others (after line 55 `app.include_router(misc_routes.router)`):

```python
app.include_router(map_routes.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_point_context.py -q`
Expected: PASS (4 passed)

- [ ] **Step 7: Run the full backend suite (no regression)**

Run: `cd backend && python -m pytest tests/ -q`
Expected: PASS (all prior tests + the new ones)

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/routes/map.py backend/app/main.py backend/tests/test_point_context.py
git commit -m "feat(api): GET /map/point-context (public, read-only, cached)"
```

---

## Task 8: Frontend layer types

**Files:**
- Create: `frontend/src/layers/types.ts`

- [ ] **Step 1: Write the types**

Create `frontend/src/layers/types.ts`:

```ts
// Layer metadata, runtime state, and point-selection result types.
// Wire shape is snake_case to mirror the backend (see src/types.ts convention).

export type LayerKind =
  | "basemap"         // exclusive; swaps the map style
  | "raster-overlay"  // tiled raster over the basemap (Phase 2: slope/hillshade)
  | "vector-overlay"  // geojson lines/fills (perimeters, future trails)
  | "marker"          // geojson points w/ symbols (saved trips, fires, point)
  | "data-overlay";   // backed by a backend provider; also feeds the dashboard

export type LayerGroup =
  | "basemap" | "terrain" | "weather" | "hazard" | "reference" | "trip";

export interface Legend {
  kind: "swatches" | "gradient" | "none";
  items?: { color: string; label: string }[];
  note?: string;
}

export interface LayerDescriptor {
  id: string;
  group: LayerGroup;
  kind: LayerKind;
  label: string;
  description?: string;
  legend?: Legend;
  providerId?: string;      // data-overlay -> backend provider id
  requiresKey?: string;     // env var that unlocks/upgrades it
  defaultVisible: boolean;
  defaultOpacity: number;   // 0..1
  supportsOpacity: boolean;
  comingSoonPhase?: number; // if set, shown disabled in the "coming soon" group
  attribution?: string;
}

export interface LayerRuntimeState { visible: boolean; opacity: number; }
export type LayerStateMap = Record<string, LayerRuntimeState>;

export type SectionStatus =
  | "ok" | "loading" | "empty" | "needs-key" | "error" | "coming-soon";

export interface PointSection {
  layer_id: string;
  title: string;
  status: SectionStatus;
  data?: Record<string, unknown> | null;
  message?: string | null;
  source?: { name: string; url?: string | null; timestamp?: string | null } | null;
}

export interface SelectionResult {
  lat: number;
  lon: number;
  place_name?: string | null;
  sections: PointSection[];
}
```

- [ ] **Step 2: Verify type check passes**

Run: `cd frontend && npx tsc -b`
Expected: no errors (exit 0)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/layers/types.ts
git commit -m "feat(layers): typed layer metadata, state, and selection-result types"
```

---

## Task 9: Hybrid basemap adapter

**Files:**
- Create: `frontend/src/layers/basemaps.ts`

- [ ] **Step 1: Write the adapter**

Create `frontend/src/layers/basemaps.ts`:

```ts
import type maplibregl from "maplibre-gl";

const GLYPHS = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf";
const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined;

export type BasemapId =
  | "basemap.street" | "basemap.satellite" | "basemap.topo"
  | "basemap.hybrid" | "basemap.dark";

const ESRI_IMAGERY =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const ESRI_REF =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}";

function raster(tiles: string[], attribution: string): maplibregl.StyleSpecification {
  return {
    version: 8,
    glyphs: GLYPHS,
    sources: { base: { type: "raster", tiles, tileSize: 256, attribution } },
    layers: [{ id: "base", type: "raster", source: "base" }],
  };
}

const FREE: Record<BasemapId, maplibregl.StyleSpecification> = {
  "basemap.street": raster(
    ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
    "© OpenStreetMap contributors",
  ),
  "basemap.topo": raster(
    ["https://tile.opentopomap.org/{z}/{x}/{y}.png"],
    "© OpenStreetMap contributors, SRTM | © OpenTopoMap (CC-BY-SA)",
  ),
  "basemap.satellite": raster([ESRI_IMAGERY], "Imagery © Esri"),
  "basemap.hybrid": {
    version: 8,
    glyphs: GLYPHS,
    sources: {
      img: { type: "raster", tiles: [ESRI_IMAGERY], tileSize: 256, attribution: "Imagery © Esri" },
      ref: { type: "raster", tiles: [ESRI_REF], tileSize: 256, attribution: "© Esri" },
    },
    layers: [
      { id: "img", type: "raster", source: "img" },
      { id: "ref", type: "raster", source: "ref" },
    ],
  },
  "basemap.dark": raster(
    ["https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"],
    "© OpenStreetMap contributors © CARTO",
  ),
};

// MapTiler style ids used when a key is configured (free tier covers low usage).
const MAPTILER_STYLE: Record<BasemapId, string> = {
  "basemap.street": "streets-v2",
  "basemap.topo": "outdoor-v2",
  "basemap.satellite": "satellite",
  "basemap.hybrid": "hybrid",
  "basemap.dark": "dataviz-dark",
};

export function hasBasemapKey(): boolean {
  return !!MAPTILER_KEY;
}

/** Returns a MapLibre style: a MapTiler style URL when a key is set, else a
 *  free no-key raster style. Both are accepted by map.setStyle(). */
export function getBasemapStyle(id: BasemapId): maplibregl.StyleSpecification | string {
  if (MAPTILER_KEY) {
    return `https://api.maptiler.com/maps/${MAPTILER_STYLE[id]}/style.json?key=${MAPTILER_KEY}`;
  }
  return FREE[id];
}
```

- [ ] **Step 2: Verify type check passes**

Run: `cd frontend && npx tsc -b`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/layers/basemaps.ts
git commit -m "feat(layers): hybrid basemap adapter (free no-key default, MapTiler upgrade)"
```

---

## Task 10: Layer registry

**Files:**
- Create: `frontend/src/layers/registry.ts`

- [ ] **Step 1: Write the registry**

Create `frontend/src/layers/registry.ts`:

```ts
import type { LayerDescriptor } from "./types";

// Order matters: panel order, and (for overlays) MapLibre draw order.
export const LAYERS: LayerDescriptor[] = [
  // --- basemaps (pick-one) ---
  { id: "basemap.street", group: "basemap", kind: "basemap", label: "Street",
    defaultVisible: false, defaultOpacity: 1, supportsOpacity: false },
  { id: "basemap.satellite", group: "basemap", kind: "basemap", label: "Satellite",
    defaultVisible: false, defaultOpacity: 1, supportsOpacity: false },
  { id: "basemap.topo", group: "basemap", kind: "basemap", label: "Topo",
    defaultVisible: true, defaultOpacity: 1, supportsOpacity: false },
  { id: "basemap.hybrid", group: "basemap", kind: "basemap", label: "Hybrid (sat + labels)",
    defaultVisible: false, defaultOpacity: 1, supportsOpacity: false },
  { id: "basemap.dark", group: "basemap", kind: "basemap", label: "Dark",
    defaultVisible: false, defaultOpacity: 1, supportsOpacity: false },

  // --- overlays (migrated; multi-toggle) ---
  { id: "overlay.perimeters", group: "hazard", kind: "vector-overlay", label: "Fire perimeters",
    defaultVisible: true, defaultOpacity: 0.18, supportsOpacity: true,
    legend: { kind: "swatches", items: [{ color: "#d84a1b", label: "Active perimeter" }] } },
  { id: "overlay.fires", group: "hazard", kind: "marker", label: "Active fires",
    defaultVisible: true, defaultOpacity: 0.75, supportsOpacity: true,
    legend: { kind: "swatches", items: [{ color: "#ff5a1f", label: "VIIRS detection" }] } },
  { id: "overlay.gpx", group: "trip", kind: "vector-overlay", label: "GPX route",
    defaultVisible: true, defaultOpacity: 0.9, supportsOpacity: true,
    legend: { kind: "swatches", items: [{ color: "#0f766e", label: "Route" }] } },
  { id: "overlay.savedTrips", group: "trip", kind: "marker", label: "Saved trips",
    defaultVisible: true, defaultOpacity: 1, supportsOpacity: false },
  { id: "overlay.point", group: "trip", kind: "marker", label: "Selected point",
    defaultVisible: true, defaultOpacity: 1, supportsOpacity: false },

  // --- coming soon (disabled previews) ---
  { id: "overlay.slope", group: "terrain", kind: "raster-overlay", label: "Slope angle",
    defaultVisible: false, defaultOpacity: 0.6, supportsOpacity: true, comingSoonPhase: 2 },
  { id: "overlay.hillshade", group: "terrain", kind: "raster-overlay", label: "Hillshade",
    defaultVisible: false, defaultOpacity: 0.6, supportsOpacity: true, comingSoonPhase: 2 },
  { id: "overlay.weather", group: "weather", kind: "data-overlay", label: "Weather / snow",
    providerId: "weather", defaultVisible: false, defaultOpacity: 1, supportsOpacity: false,
    comingSoonPhase: 3 },
];

export const BASEMAP_LAYERS = LAYERS.filter((l) => l.group === "basemap");
export const OVERLAY_LAYERS = LAYERS.filter((l) => l.group !== "basemap" && !l.comingSoonPhase);
export const COMING_SOON_LAYERS = LAYERS.filter((l) => !!l.comingSoonPhase);
```

- [ ] **Step 2: Verify type check passes**

Run: `cd frontend && npx tsc -b`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/layers/registry.ts
git commit -m "feat(layers): layer registry (basemaps, migrated overlays, coming-soon)"
```

---

## Task 11: Layer state helpers

**Files:**
- Create: `frontend/src/layers/layerState.ts`

- [ ] **Step 1: Write the helpers**

Create `frontend/src/layers/layerState.ts`:

```ts
import { LAYERS } from "./registry";
import type { LayerStateMap } from "./types";

/** Initial state from registry defaults — reproduces today's defaults
 *  (topo basemap, all overlays visible). */
export function seedLayerState(): LayerStateMap {
  const state: LayerStateMap = {};
  for (const l of LAYERS) {
    state[l.id] = { visible: l.defaultVisible, opacity: l.defaultOpacity };
  }
  return state;
}

export function setVisible(state: LayerStateMap, id: string, visible: boolean): LayerStateMap {
  return { ...state, [id]: { ...state[id], visible } };
}

export function setOpacity(state: LayerStateMap, id: string, opacity: number): LayerStateMap {
  return { ...state, [id]: { ...state[id], opacity } };
}

/** Basemaps are pick-one: selecting one makes the others invisible. */
export function selectBasemap(state: LayerStateMap, id: string): LayerStateMap {
  const next = { ...state };
  for (const l of LAYERS) {
    if (l.group === "basemap") next[l.id] = { ...next[l.id], visible: l.id === id };
  }
  return next;
}

export function activeBasemapId(state: LayerStateMap): string {
  const found = LAYERS.find((l) => l.group === "basemap" && state[l.id]?.visible);
  return found ? found.id : "basemap.topo";
}

/** Provider ids for currently-visible data-overlay layers (sent to point-context). */
export function enabledDataProviderIds(state: LayerStateMap): string[] {
  return LAYERS
    .filter((l) => l.kind === "data-overlay" && l.providerId && state[l.id]?.visible)
    .map((l) => l.providerId as string);
}
```

- [ ] **Step 2: Verify type check passes**

Run: `cd frontend && npx tsc -b`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/layers/layerState.ts
git commit -m "feat(layers): layer-state seeding and update helpers"
```

---

## Task 12: API client — pointContext

**Files:**
- Modify: `frontend/src/lib/api.ts:1-12` (imports) and the `api` object (after `searchLocation`)

- [ ] **Step 1: Add the import**

In `frontend/src/lib/api.ts`, add below the existing `import type { ... } from "../types";` block (after line 12):

```ts
import type { SelectionResult } from "../layers/types";
```

- [ ] **Step 2: Add the client method**

In the `api` object in `frontend/src/lib/api.ts`, add this method immediately after the `searchLocation: (...) => ...,` entry:

```ts
  pointContext: (lat: number, lon: number, layers?: string[]) => {
    const q = new URLSearchParams({ lat: String(lat), lon: String(lon) });
    if (layers && layers.length) q.set("layers", layers.join(","));
    return request<SelectionResult>(`/map/point-context?${q.toString()}`);
  },
```

- [ ] **Step 3: Verify type check passes**

Run: `cd frontend && npx tsc -b`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(api-client): pointContext(lat, lon, layers)"
```

---

## Task 13: Legend component

**Files:**
- Create: `frontend/src/components/Legend.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/Legend.tsx`:

```tsx
import type { Legend as LegendType } from "../layers/types";

export default function Legend({ legend }: { legend: LegendType }) {
  if (!legend || legend.kind === "none" || !legend.items?.length) return null;
  return (
    <div className="legend">
      {legend.items.map((it) => (
        <span key={it.label} className="legend-item">
          <span className="legend-swatch" style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
      {legend.note ? <span className="legend-note">{legend.note}</span> : null}
    </div>
  );
}
```

- [ ] **Step 2: Verify type check passes**

Run: `cd frontend && npx tsc -b`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Legend.tsx
git commit -m "feat(ui): Legend component for analytical layers"
```

---

## Task 14: LayersControl (floating panel)

**Files:**
- Create: `frontend/src/components/LayersControl.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/LayersControl.tsx`:

```tsx
import { useState } from "react";
import type { LayerStateMap } from "../layers/types";
import { BASEMAP_LAYERS, OVERLAY_LAYERS, COMING_SOON_LAYERS } from "../layers/registry";
import { activeBasemapId } from "../layers/layerState";
import Legend from "./Legend";

interface Props {
  layerState: LayerStateMap;
  onSelectBasemap: (id: string) => void;
  onToggle: (id: string, visible: boolean) => void;
  onOpacity: (id: string, opacity: number) => void;
}

export default function LayersControl({ layerState, onSelectBasemap, onToggle, onOpacity }: Props) {
  const [open, setOpen] = useState(false);
  const activeBase = activeBasemapId(layerState);

  return (
    <div className="layers-control">
      <button className="layers-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        ▤ Layers
      </button>
      {open && (
        <div className="layers-panel" role="group" aria-label="Map layers">
          <div className="layers-panel-head">
            <strong>Layers</strong>
            <button className="layers-close" aria-label="Close layers" onClick={() => setOpen(false)}>✕</button>
          </div>

          <div className="layers-group">
            <div className="layers-group-label">Basemap</div>
            {BASEMAP_LAYERS.map((l) => (
              <label key={l.id} className="layers-row">
                <input
                  type="radio"
                  name="basemap"
                  checked={activeBase === l.id}
                  onChange={() => onSelectBasemap(l.id)}
                />
                {l.label}
              </label>
            ))}
          </div>

          <div className="layers-group">
            <div className="layers-group-label">Overlays</div>
            {OVERLAY_LAYERS.map((l) => {
              const st = layerState[l.id];
              return (
                <div key={l.id} className="layers-row-block">
                  <label className="layers-row">
                    <input
                      type="checkbox"
                      checked={!!st?.visible}
                      onChange={(e) => onToggle(l.id, e.target.checked)}
                    />
                    {l.label}
                  </label>
                  {l.legend ? <Legend legend={l.legend} /> : null}
                  {l.supportsOpacity && st?.visible ? (
                    <div className="layers-opacity">
                      <span>opacity</span>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={st.opacity}
                        onChange={(e) => onOpacity(l.id, Number(e.target.value))}
                      />
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>

          <div className="layers-group layers-group-disabled">
            <div className="layers-group-label">Coming soon</div>
            {COMING_SOON_LAYERS.map((l) => (
              <label key={l.id} className="layers-row" title={`Arrives in Phase ${l.comingSoonPhase}`}>
                <input type="checkbox" disabled />
                {l.label}
                <span className="layers-phase-badge">Phase {l.comingSoonPhase}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify type check passes**

Run: `cd frontend && npx tsc -b`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/LayersControl.tsx
git commit -m "feat(ui): floating LayersControl panel (basemap, overlays, opacity, coming-soon)"
```

---

## Task 15: PointDashboard ("This point")

**Files:**
- Create: `frontend/src/components/PointDashboard.tsx`

- [ ] **Step 1: Write the component**

Create `frontend/src/components/PointDashboard.tsx`:

```tsx
import type { SelectionResult, PointSection } from "../layers/types";

interface Props {
  coords: { lat: number; lon: number } | null;
  result: SelectionResult | null;
  loading: boolean;
  error: string | null;
}

const STATUS_LABEL: Record<string, string> = {
  ok: "ok",
  loading: "loading…",
  empty: "no data",
  error: "error",
  "needs-key": "needs key",
  "coming-soon": "coming soon",
};

function ElevationValue({ data }: { data: Record<string, unknown> | null | undefined }) {
  const ft = data?.elevation_ft as number | undefined;
  return <div className="point-elev">{ft != null ? `${ft.toLocaleString()} ft` : "—"}</div>;
}

function SectionCard({ s }: { s: PointSection }) {
  return (
    <div className={`point-section point-${s.status}`}>
      <div className="point-section-head">
        <span className="point-section-title">{s.title}</span>
        <span className="point-section-status">{STATUS_LABEL[s.status] ?? s.status}</span>
      </div>
      {s.layer_id === "elevation" && s.status === "ok" ? <ElevationValue data={s.data} /> : null}
      {s.message ? <div className="point-section-msg">{s.message}</div> : null}
      {s.source ? (
        <div className="point-section-src">
          {s.source.url ? (
            <a href={s.source.url} target="_blank" rel="noreferrer">{s.source.name}</a>
          ) : (
            s.source.name
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function PointDashboard({ coords, result, loading, error }: Props) {
  if (!coords) {
    return (
      <div className="empty-note">
        Click the map to inspect a point — elevation now, and more as layers ship.
      </div>
    );
  }
  return (
    <div className="point-dashboard">
      <div className="point-head">
        <div className="point-place">{result?.place_name || "Selected point"}</div>
        <div className="point-coords">{coords.lat.toFixed(4)}, {coords.lon.toFixed(4)}</div>
      </div>
      {error ? <div className="point-error">{error}</div> : null}
      {loading && !result ? (
        <div className="point-skeleton">Loading point context…</div>
      ) : (
        (result?.sections || []).map((s) => <SectionCard key={s.layer_id} s={s} />)
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify type check passes**

Run: `cd frontend && npx tsc -b`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/PointDashboard.tsx
git commit -m "feat(ui): PointDashboard live point-context panel with status states"
```

---

## Task 16: Refactor MapView to render from registry/state

**Files:**
- Modify: `frontend/src/components/MapView.tsx` (full replacement)

This keeps every data prop and behavior; it swaps the `layers: LayerState` prop for `layerState: LayerStateMap`, drives the basemap via the adapter, and drives overlay visibility/opacity from the registry/state.

- [ ] **Step 1: Replace the file**

Replace the entire contents of `frontend/src/components/MapView.tsx` with:

```tsx
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Trip } from "../types";
import type { LayerStateMap } from "../layers/types";
import { getBasemapStyle, type BasemapId } from "../layers/basemaps";
import { activeBasemapId } from "../layers/layerState";

export interface FireDetection {
  latitude: number;
  longitude: number;
  distance_miles?: number;
  confidence?: string | number;
  acq_date?: string;
}

// Maps a registry overlay id -> its MapLibre layer ids + opacity paint props.
const OVERLAY_RENDER: Record<string, { layerIds: string[]; opacity?: [string, string][] }> = {
  "overlay.perimeters": {
    layerIds: ["perims-fill", "perims-line"],
    opacity: [["perims-fill", "fill-opacity"], ["perims-line", "line-opacity"]],
  },
  "overlay.fires": {
    layerIds: ["fires-circle"],
    opacity: [["fires-circle", "circle-opacity"]],
  },
  "overlay.gpx": {
    layerIds: ["gpx-line"],
    opacity: [["gpx-line", "line-opacity"]],
  },
  "overlay.savedTrips": {
    layerIds: ["trips-circle", "trips-label"],
  },
};

interface Props {
  layerState: LayerStateMap;
  trips: Trip[];
  selectedTripId: number | null;
  selectedPoint: { lat: number; lon: number } | null;
  flyTo: { lat: number; lon: number; zoom?: number } | null;
  gpxPoints: [number, number, number | null][] | null; // [lat, lon, ele]
  fireDetections: FireDetection[];
  perimeterGeojson: GeoJSON.FeatureCollection | null;
  onSelectPoint: (lat: number, lon: number) => void;
  onSelectTrip: (id: number) => void;
}

const EMPTY_FC: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export default function MapView({
  layerState, trips, selectedTripId, selectedPoint, flyTo, gpxPoints,
  fireDetections, perimeterGeojson, onSelectPoint, onSelectTrip,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const readyRef = useRef(false);
  const activeBaseRef = useRef<string>(activeBasemapId(layerState));
  const handlersRef = useRef({ onSelectPoint, onSelectTrip });
  handlersRef.current = { onSelectPoint, onSelectTrip };

  // ---- init once ----
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: getBasemapStyle(activeBasemapId(layerState) as BasemapId),
      center: [-110.5, 41.5],
      zoom: 4,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "imperial" }), "bottom-left");

    map.on("load", () => {
      addOverlaySources(map);
      readyRef.current = true;
      syncAll();
    });
    map.on("styledata", () => {
      if (!readyRef.current) return;
      if (!map.getSource("trips")) {
        addOverlaySources(map);
        syncAll();
      }
    });

    map.on("click", (e) => {
      const feats = map.queryRenderedFeatures(e.point, { layers: ["trips-circle"] });
      if (feats.length > 0) {
        const id = feats[0].properties?.id;
        if (id != null) handlersRef.current.onSelectTrip(Number(id));
        return;
      }
      handlersRef.current.onSelectPoint(e.lngLat.lat, e.lngLat.lng);
    });

    map.on("mouseenter", "trips-circle", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", "trips-circle", () => (map.getCanvas().style.cursor = ""));
    map.on("click", "fires-circle", (e) => {
      const p = e.features?.[0]?.properties || {};
      new maplibregl.Popup({ closeButton: false })
        .setLngLat(e.lngLat)
        .setHTML(
          `<div class="p-title">Active fire detection</div>
           <div class="p-meta">date: ${p.acq_date || "?"} · conf: ${p.confidence ?? "?"} · ${p.distance_miles != null ? Number(p.distance_miles).toFixed(1) + " mi away" : ""}</div>`,
        )
        .addTo(map);
    });

    return () => {
      map.remove();
      mapRef.current = null;
      readyRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function addOverlaySources(map: maplibregl.Map) {
    if (map.getSource("trips")) return;
    map.addSource("trips", { type: "geojson", data: EMPTY_FC });
    map.addSource("gpx", { type: "geojson", data: EMPTY_FC });
    map.addSource("fires", { type: "geojson", data: EMPTY_FC });
    map.addSource("perims", { type: "geojson", data: EMPTY_FC });

    map.addLayer({
      id: "perims-fill", type: "fill", source: "perims",
      paint: { "fill-color": "#d84a1b", "fill-opacity": 0.18 },
    });
    map.addLayer({
      id: "perims-line", type: "line", source: "perims",
      paint: { "line-color": "#d84a1b", "line-width": 1.6, "line-dasharray": [3, 2] },
    });
    map.addLayer({
      id: "fires-circle", type: "circle", source: "fires",
      paint: {
        "circle-radius": 6, "circle-color": "#ff5a1f", "circle-opacity": 0.75,
        "circle-stroke-color": "#7c1d05", "circle-stroke-width": 1.4,
      },
    });
    map.addLayer({
      id: "gpx-line", type: "line", source: "gpx",
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#0f766e", "line-width": 3.2, "line-opacity": 0.9 },
    });
    map.addLayer({
      id: "trips-circle", type: "circle", source: "trips",
      paint: {
        "circle-radius": ["case", ["get", "selected"], 9, 7],
        "circle-color": ["case", ["get", "selected"], "#d84a1b", "#1f241f"],
        "circle-stroke-color": "#fbfaf6", "circle-stroke-width": 2,
      },
    });
    map.addLayer({
      id: "trips-label", type: "symbol", source: "trips",
      layout: {
        "text-field": ["get", "name"],
        "text-size": 11,
        "text-offset": [0, 1.3],
        "text-anchor": "top",
        "text-font": ["Noto Sans Regular"],
        "text-optional": true,
      },
      paint: { "text-color": "#1f241f", "text-halo-color": "#fbfaf6", "text-halo-width": 1.4 },
    });
  }

  function setData(id: string, data: GeoJSON.FeatureCollection) {
    const src = mapRef.current?.getSource(id) as maplibregl.GeoJSONSource | undefined;
    src?.setData(data);
  }

  function setVisible(layerIds: string[], visible: boolean) {
    const map = mapRef.current;
    if (!map) return;
    for (const id of layerIds) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visible ? "visible" : "none");
    }
  }

  function syncAll() {
    syncTrips(); syncGpx(); syncFires(); syncPerims(); syncVisibility(); syncMarker();
  }

  function syncTrips() {
    setData("trips", {
      type: "FeatureCollection",
      features: trips.map((t) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [t.longitude, t.latitude] },
        properties: { id: t.id, name: t.name, selected: t.id === selectedTripId },
      })),
    });
  }
  function syncGpx() {
    if (!gpxPoints || gpxPoints.length < 2) { setData("gpx", EMPTY_FC); return; }
    setData("gpx", {
      type: "FeatureCollection",
      features: [{
        type: "Feature",
        geometry: { type: "LineString", coordinates: gpxPoints.map((p) => [p[1], p[0]]) },
        properties: {},
      }],
    });
  }
  function syncFires() {
    setData("fires", {
      type: "FeatureCollection",
      features: fireDetections.map((f) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [f.longitude, f.latitude] },
        properties: {
          distance_miles: f.distance_miles, confidence: f.confidence, acq_date: f.acq_date,
        },
      })),
    });
  }
  function syncPerims() { setData("perims", perimeterGeojson || EMPTY_FC); }

  function syncVisibility() {
    const map = mapRef.current;
    if (!map) return;
    for (const [id, render] of Object.entries(OVERLAY_RENDER)) {
      const st = layerState[id];
      setVisible(render.layerIds, !!st?.visible);
      if (render.opacity && st) {
        for (const [layerId, prop] of render.opacity) {
          if (map.getLayer(layerId)) map.setPaintProperty(layerId, prop, st.opacity);
        }
      }
    }
  }

  function syncMarker() {
    const map = mapRef.current;
    if (!map) return;
    const pointVisible = layerState["overlay.point"]?.visible ?? true;
    if (selectedPoint && pointVisible) {
      if (!markerRef.current) {
        const el = document.createElement("div");
        el.innerHTML =
          `<svg width="28" height="34" viewBox="0 0 28 34"><path d="M14 0C6.8 0 1 5.8 1 13c0 9.6 13 21 13 21s13-11.4 13-21C27 5.8 21.2 0 14 0z" fill="#d84a1b" stroke="#7c1d05" stroke-width="1.4"/><circle cx="14" cy="13" r="4.6" fill="#fbfaf6"/></svg>`;
        markerRef.current = new maplibregl.Marker({ element: el, anchor: "bottom" });
      }
      markerRef.current.setLngLat([selectedPoint.lon, selectedPoint.lat]).addTo(map);
    } else {
      markerRef.current?.remove();
    }
  }

  // ---- prop-driven syncs ----
  useEffect(() => { if (readyRef.current) syncTrips(); }, [trips, selectedTripId]);
  useEffect(() => { if (readyRef.current) syncGpx(); }, [gpxPoints]);
  useEffect(() => { if (readyRef.current) syncFires(); }, [fireDetections]);
  useEffect(() => { if (readyRef.current) syncPerims(); }, [perimeterGeojson]);
  useEffect(() => { if (readyRef.current) syncVisibility(); }, [layerState]);
  useEffect(() => { syncMarker(); }, [selectedPoint, layerState]);

  // basemap swap (only when the active basemap actually changes)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const next = activeBasemapId(layerState);
    if (next !== activeBaseRef.current) {
      activeBaseRef.current = next;
      map.setStyle(getBasemapStyle(next as BasemapId));
    }
  }, [layerState]);

  // fly to target
  useEffect(() => {
    if (!flyTo || !mapRef.current) return;
    mapRef.current.flyTo({ center: [flyTo.lon, flyTo.lat], zoom: flyTo.zoom ?? 11, duration: 1400 });
  }, [flyTo]);

  return (
    <>
      <div ref={containerRef} className="map-container" />
      {selectedPoint && (
        <div className="coord-readout">
          {selectedPoint.lat.toFixed(5)}, {selectedPoint.lon.toFixed(5)}
        </div>
      )}
      <div className="map-overlay-br">click map to set trip point</div>
    </>
  );
}
```

- [ ] **Step 2: Verify type check passes**

Run: `cd frontend && npx tsc -b`
Expected: errors in `App.tsx` and `PlanPanel.tsx` only — both still reference the removed `LayerState` export (`App.tsx` passes `layers=`/imports `LayerState`; `PlanPanel.tsx` imports `LayerState` from `./MapView`). These are fixed in Task 17. `MapView.tsx` itself must have no errors; confirm every reported error points at `App.tsx` or `PlanPanel.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MapView.tsx
git commit -m "refactor(map): render basemap + overlay visibility/opacity from layer registry/state"
```

---

## Task 17: Wire App.tsx (state, point-inspect, mount control + dashboard)

**Files:**
- Modify: `frontend/src/App.tsx` (imports, state, handlers, render)
- Modify: `frontend/src/components/PlanPanel.tsx` (drop map-layers block + props)

- [ ] **Step 1: Update imports in App.tsx**

In `frontend/src/App.tsx`, change the MapView import (line 6) from:

```ts
import MapView, { type FireDetection, type LayerState } from "./components/MapView";
```

to:

```ts
import MapView, { type FireDetection } from "./components/MapView";
import LayersControl from "./components/LayersControl";
import PointDashboard from "./components/PointDashboard";
import type { LayerStateMap, SelectionResult } from "./layers/types";
import {
  seedLayerState, setVisible as setLayerVisible, setOpacity as setLayerOpacity,
  selectBasemap, enabledDataProviderIds,
} from "./layers/layerState";
```

- [ ] **Step 2: Replace the layer state declaration**

In `frontend/src/App.tsx`, replace the whole `const [layers, setLayers] = useState<LayerState>({ ... });` block (lines 124-131) with:

```ts
  const [layerState, setLayerState] = useState<LayerStateMap>(seedLayerState());

  // live point-context ("This point" dashboard)
  const [pointResult, setPointResult] = useState<SelectionResult | null>(null);
  const [pointLoading, setPointLoading] = useState(false);
  const [pointError, setPointError] = useState<string | null>(null);
  const pointCacheRef = useRef<Map<string, SelectionResult>>(new Map());
```

- [ ] **Step 3: Add the point-inspect helper**

In `frontend/src/App.tsx`, add this function immediately before `function onSearchResult(r: SearchResult) {` (around line 287):

```ts
  async function inspectPoint(lat: number, lon: number) {
    const key = `${lat.toFixed(4)},${lon.toFixed(4)}`;
    const cached = pointCacheRef.current.get(key);
    if (cached) {
      setPointResult(cached);
      setPointError(null);
      setPointLoading(false);
      return;
    }
    setPointLoading(true);
    setPointError(null);
    setPointResult(null);
    try {
      const res = await api.pointContext(lat, lon, enabledDataProviderIds(layerState));
      pointCacheRef.current.set(key, res);
      setPointResult(res);
    } catch (e) {
      setPointError((e as Error).message);
    } finally {
      setPointLoading(false);
    }
  }
```

- [ ] **Step 4: Call inspectPoint from the three entry points**

In `frontend/src/App.tsx`:

In `onSearchResult` (after `setFlyTo({ lat: r.latitude, lon: r.longitude, zoom: 11 });`) add:

```ts
    inspectPoint(r.latitude, r.longitude);
```

In `onMapSelect` (after `setPointName(null);`) add:

```ts
    inspectPoint(lat, lon);
```

In `selectTrip` (after `setFlyTo({ lat: trip.latitude, lon: trip.longitude, zoom: 10 });`) add:

```ts
    inspectPoint(trip.latitude, trip.longitude);
```

- [ ] **Step 5: Mount LayersControl over the map**

In `frontend/src/App.tsx`, inside `<main className="panel-center">`, replace the MapView `layers={layers}` prop with `layerState={layerState}`, and add the `LayersControl` right after the `<div className="map-overlay-tl">…</div>` block (before `</main>`):

```tsx
            <div className="map-overlay-tr">
              <LayersControl
                layerState={layerState}
                onSelectBasemap={(id) => setLayerState((s) => selectBasemap(s, id))}
                onToggle={(id, v) => setLayerState((s) => setLayerVisible(s, id, v))}
                onOpacity={(id, o) => setLayerState((s) => setLayerOpacity(s, id, o))}
              />
            </div>
```

- [ ] **Step 6: Add PointDashboard to the right panel (desktop + mobile)**

In `frontend/src/App.tsx`, in the desktop `<aside className="panel-right">`, render the dashboard above the existing conditions. Replace:

```tsx
            <aside className="panel-right">
              {user ? (
                <ConditionDashboard
```

with:

```tsx
            <aside className="panel-right">
              <div className="section">
                <h2 className="section-title">This point</h2>
                <PointDashboard
                  coords={selectedPoint}
                  result={pointResult}
                  loading={pointLoading}
                  error={pointError}
                />
              </div>
              {user ? (
                <ConditionDashboard
```

And in the mobile Conditions tab, do the same: replace the mobile `mobileTab === "conditions" ? (` block's first child `user ? (` with the `PointDashboard` rendered first, e.g. wrap:

```tsx
                {mobileTab === "conditions" ? (
                  <>
                    <div className="section">
                      <h2 className="section-title">This point</h2>
                      <PointDashboard
                        coords={selectedPoint}
                        result={pointResult}
                        loading={pointLoading}
                        error={pointError}
                      />
                    </div>
                    {user ? (
                      <ConditionDashboard
                        trip={selectedTrip}
                        check={check}
                        liveStatus={liveStatus}
                        running={running}
                        loadingCheck={loadingCheck}
                        error={dashError}
                        staleHours={settings?.stale_hours ?? 24}
                        onRunCheck={runCheck}
                        onRegenerateSummary={regenerateSummary}
                        regenBusy={regenBusy}
                      />
                    ) : (
                      <LoggedOutConditions onLogin={() => setView("auth")} />
                    )}
                  </>
                ) : (
```

(Remove the now-duplicated original `user ? (<ConditionDashboard ... />) : (<LoggedOutConditions .../>)` that previously sat directly under `mobileTab === "conditions" ? (`.)

- [ ] **Step 7: Update both PlanPanel usages (drop layer props)**

In `frontend/src/App.tsx`, remove `layers={layers}` and `onLayersChange={setLayers}` from **both** `<PlanPanel ... />` usages (desktop ~line 380 and mobile ~line 490). Leave all other props unchanged.

- [ ] **Step 8: Update PlanPanel to drop the map-layers block**

Replace the entire contents of `frontend/src/components/PlanPanel.tsx` with:

```tsx
import type { Trip } from "../types";
import TripForm from "./TripForm";
import SavedTrips from "./SavedTrips";

interface Props {
  loggedIn: boolean;
  selectedPoint: { lat: number; lon: number } | null;
  pointName: string | null;
  trips: Trip[];
  selectedTripId: number | null;
  runningAll: boolean;
  onTripCreated: (trip: Trip) => void;
  onSelectTrip: (trip: Trip) => void;
  onOpenDetail: (trip: Trip) => void;
  onRunAll: () => void;
  onLoginClick: () => void;
}

export default function PlanPanel({
  loggedIn, selectedPoint, pointName, trips, selectedTripId, runningAll,
  onTripCreated, onSelectTrip, onOpenDetail, onRunAll, onLoginClick,
}: Props) {
  return (
    <>
      {loggedIn ? (
        <>
          <div className="section">
            <h2 className="section-title">New trip</h2>
            <TripForm selectedPoint={selectedPoint} locationName={pointName} onCreated={onTripCreated} />
          </div>
          <div className="section">
            <h2 className="section-title">Saved trips ({trips.length})</h2>
            <SavedTrips
              trips={trips}
              selectedTripId={selectedTripId}
              onSelect={onSelectTrip}
              onOpenDetail={onOpenDetail}
              onRunAll={onRunAll}
              runningAll={runningAll}
            />
          </div>
        </>
      ) : (
        <div className="section">
          <div className="empty-note">
            Log in to save trips and run condition checks. You can browse and search the map without an account.
          </div>
          <button className="btn primary" style={{ marginTop: 8 }} onClick={onLoginClick}>Log in / Sign up</button>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 9: Verify type check passes**

Run: `cd frontend && npx tsc -b`
Expected: no errors

- [ ] **Step 10: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/PlanPanel.tsx
git commit -m "feat(app): LayerStateMap, floating LayersControl, live PointDashboard; drop PlanPanel layer block"
```

---

## Task 18: Styles for the new components

**Files:**
- Modify: `frontend/src/index.css` (the project's global stylesheet, already imported by `main.tsx`; it defines `.map-overlay-tl`, `.coord-readout`, etc.).

- [ ] **Step 1: Append component styles**

Append to `frontend/src/index.css` (these literal colors match the app palette already used in that file):

```css
/* --- floating layers control --- */
.map-overlay-tr { position: absolute; top: 12px; right: 12px; z-index: 5; }
.layers-control { display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
.layers-toggle {
  background: #1f241f; color: #fbfaf6; border: none; border-radius: 6px;
  padding: 6px 10px; font-size: 13px; cursor: pointer; box-shadow: 0 2px 8px rgba(0,0,0,.2);
}
.layers-panel {
  width: 240px; max-height: 70vh; overflow-y: auto; background: #fbfaf6;
  border: 1px solid #e7e3d9; border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,.18);
  font-size: 13px;
}
.layers-panel-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 10px; border-bottom: 1px solid #e7e3d9;
}
.layers-close { background: none; border: none; cursor: pointer; font-size: 14px; color: #8a8575; }
.layers-group { padding: 8px 10px; border-top: 1px solid #e7e3d9; }
.layers-group:first-of-type { border-top: none; }
.layers-group-label {
  font-size: 10px; letter-spacing: .05em; text-transform: uppercase; color: #8a8575; margin-bottom: 4px;
}
.layers-row { display: flex; align-items: center; gap: 6px; padding: 3px 0; cursor: pointer; }
.layers-row-block { padding: 2px 0; }
.layers-opacity { display: flex; align-items: center; gap: 6px; margin: 2px 0 4px 18px; font-size: 11px; color: #8a8575; }
.layers-opacity input[type="range"] { flex: 1; }
.layers-group-disabled { opacity: .55; }
.layers-phase-badge { margin-left: auto; background: #e7e3d9; border-radius: 8px; padding: 0 6px; font-size: 9px; }
.legend { display: flex; flex-wrap: wrap; gap: 8px; margin: 2px 0 2px 18px; font-size: 11px; color: #555; }
.legend-item { display: inline-flex; align-items: center; gap: 4px; }
.legend-swatch { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.legend-note { color: #8a8575; }

/* --- this-point dashboard --- */
.point-dashboard { display: flex; flex-direction: column; gap: 7px; }
.point-head .point-place { font-weight: 600; }
.point-head .point-coords { color: #8a8575; font-size: 11px; }
.point-section { border: 1px solid #e7e3d9; border-radius: 6px; padding: 7px 9px; background: #fff; }
.point-section.point-coming-soon, .point-section.point-empty { border-style: dashed; background: transparent; }
.point-section-head { display: flex; justify-content: space-between; align-items: center; }
.point-section-title { font-size: 10px; letter-spacing: .04em; text-transform: uppercase; color: #8a8575; }
.point-section-status { font-size: 10px; color: #8a8575; }
.point-section.point-ok .point-section-status { color: #3a5a40; }
.point-section.point-error .point-section-status { color: #b00020; }
.point-elev { font-size: 18px; font-weight: 700; }
.point-section-msg { color: #8a8575; font-size: 12px; }
.point-section-src { font-size: 10px; color: #8a8575; }
.point-skeleton { color: #8a8575; font-size: 12px; padding: 8px 0; }
.point-error { color: #b00020; font-size: 12px; }
```

- [ ] **Step 2: Verify the build**

Run: `cd frontend && npm run build`
Expected: build succeeds (tsc + vite). No type or build errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "style: floating layers control, legends, and point dashboard"
```

---

## Task 19: Docs + final verification (coexistence smoke test)

**Files:**
- Modify: `README.md`, `.env.example`

- [ ] **Step 1: Document the optional MapTiler key**

Add to `.env.example` (frontend section):

```bash
# Optional: a MapTiler API key (free tier) upgrades basemaps to crisp vector
# styles and unlocks terrain tiles reused in later phases. Leave unset to use
# the free no-key raster basemaps. https://www.maptiler.com/
VITE_MAPTILER_KEY=
```

Add a short note under the README "Other features" → Map bullet:

```markdown
- **Map layers:** floating Layers control with five basemaps (street / satellite / topo / hybrid / dark), per-overlay visibility + opacity, and legends. Basemaps run fully free with no API key; set `VITE_MAPTILER_KEY` (free tier) to upgrade to MapTiler vector styles. Click any point for a live **"This point"** dashboard (elevation now; slope/aspect/weather arrive in later phases).
```

- [ ] **Step 2: Commit the docs**

```bash
git add README.md .env.example
git commit -m "docs: document map layers + optional VITE_MAPTILER_KEY"
```

- [ ] **Step 3: Full backend test run**

Run: `cd backend && python -m pytest tests/ -q`
Expected: all pass (existing suite + `test_providers.py` + `test_point_context.py`).

- [ ] **Step 4: Full frontend build**

Run: `cd frontend && npm run build`
Expected: succeeds with no errors.

- [ ] **Step 5: Manual coexistence smoke test**

Start both servers (see README), then verify in the browser:

1. **Basemaps:** open the floating Layers control; switch among all five basemaps — each renders. (With no key, satellite/hybrid use Esri, dark uses CARTO.)
2. **Overlays migrated:** saved-trip markers, selected-point marker, GPX route all render and toggle on/off; opacity sliders on fires/perimeters/GPX change opacity. Defaults match the old app (topo + all overlays on).
3. **This point:** click anywhere on the map → "This point" shows place name + elevation (with USGS/Open-Meteo source); slope/aspect and weather show "coming soon"; works when logged out.
4. **Coexistence (critical):** log in, select a saved trip, click **Run condition check** → it runs to completion exactly as before; fire detections + perimeters still appear on the map after the check; trip detail and print report still work.

Confirm each of the four. If any fails, fix before declaring done (do not commit a broken state).

- [ ] **Step 6: Final commit (if any fixes were needed)**

```bash
git add -A
git commit -m "fix: address issues found in Phase 1 manual verification"
```

(If no fixes were needed, skip this step.)

---

## Self-Review (completed by plan author)

**Spec coverage:**
- Layer system foundation (FE registry + BE providers + aggregator) → Tasks 1-12.
- Four interfaces (metadata/state/provider/selection) → Tasks 1, 8.
- Hybrid basemaps (free + MapTiler via env var) → Task 9, 19.
- Floating Layers control (groups, opacity, legend, coming-soon) → Tasks 13, 14.
- Live "This point" dashboard with all status states → Task 15, 17.
- Migration of existing overlays, zero regression → Tasks 16, 17 (+ smoke test Task 19 step 5).
- Caching (backend TTL/LRU + frontend point cache) → Tasks 6, 17.
- Coexistence guarantee → no changes to check pipeline; backend suite re-run (Task 7 step 7, Task 19 step 3); manual smoke (Task 19 step 5).
- Place-name as always-on provider → Task 3.
- Config (`VITE_MAPTILER_KEY`) → Task 19.

**Type consistency:** Provider `id/title/requires_key/always_on` used uniformly (Tasks 1-6). Wire fields `layer_id`/`place_name`/`status` consistent between aggregator (Task 6), schemas (Task 7), and frontend types (Task 8). `getBasemapStyle`/`activeBasemapId`/`selectBasemap`/`enabledDataProviderIds` names match across Tasks 9-17.

**Placeholder scan:** No TBD/TODO-as-gap. The only `TODO(...)` markers are intentional stub-replacement signposts in `stubs.py` (Task 4), per spec.
