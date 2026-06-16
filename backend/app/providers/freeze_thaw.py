"""Freeze/thaw point provider — derived from the NWS forecast (wraps nws_weather)
plus a refreeze heuristic. Elevation lapse + solar aspect are layered in by the
dashboard using the elevation/slope_aspect sections; this card focuses on the
freeze timing the forecast gives directly."""
from __future__ import annotations
from ..connectors import nws_weather
from .base import ProviderContext, ProviderResult, ok, empty, error
from ._wrap import connector_ctx

FREEZING_F = 32
REFREEZE_LOW_F = 28


class FreezeThawProvider:
    id = "freeze_thaw"
    title = "Freeze / thaw"
    requires_key = None
    always_on = True

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        try:
            cout = nws_weather.run(connector_ctx(ctx.latitude, ctx.longitude))
            n = cout.normalized or {}
            hourly = [h for h in (n.get("hourly_sample") or [])
                      if h.get("temperature_f") is not None]
            if not hourly:
                return empty(self.id, self.title, "No hourly forecast for this point")
            temps = [h["temperature_f"] for h in hourly[:24]]
            below = sum(1 for t in temps if t < FREEZING_F)
            overnight_low = min(temps)
            high = n.get("high_f")
            if overnight_low < REFREEZE_LOW_F and (high is None or high > FREEZING_F):
                refreeze = "likely"
            elif overnight_low < FREEZING_F:
                refreeze = "marginal"
            else:
                refreeze = "no"
            return ok(self.id, self.title, data={
                "overnight_low_f": round(overnight_low),
                "hours_below_freezing": below,
                "refreeze": refreeze,
            }, source_name="Derived from NWS hourly forecast",
               source_url="https://www.weather.gov/")
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
