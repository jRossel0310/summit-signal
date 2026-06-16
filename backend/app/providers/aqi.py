"""AQI point provider — wraps the airnow connector (current AQI within 75 mi)."""
from __future__ import annotations
from ..connectors import airnow
from ..services.settings_service import get_api_key
from .base import ProviderContext, ProviderResult, ok, empty, needs_key, error
from ._wrap import connector_ctx


class AqiProvider:
    id = "aqi"
    title = "Air quality (AQI)"
    requires_key = "airnow"
    always_on = False

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        if not get_api_key(None, "airnow"):
            return needs_key(self.id, self.title, "SUMMIT_SIGNAL_AIRNOW_KEY")
        try:
            cout = airnow.run(connector_ctx(ctx.latitude, ctx.longitude))
            n = cout.normalized or {}
            readings = n.get("readings") or []
            if not readings:
                return empty(self.id, self.title, "No AQI monitors within 75 miles")
            top = max(readings, key=lambda r: r.get("aqi") or -1)
            return ok(self.id, self.title, data={
                "max_aqi": n.get("max_aqi"),
                "category": top.get("category"),
                "parameter": top.get("parameter"),
                "reporting_area": top.get("reporting_area"),
            }, source_name="AirNow (US EPA partner network)",
               source_url="https://www.airnow.gov/")
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
