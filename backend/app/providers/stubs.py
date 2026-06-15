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
