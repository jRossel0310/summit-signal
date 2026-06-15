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
