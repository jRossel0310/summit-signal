"""Wildfire point provider — nearest active fire (wraps nasa_firms)."""
from __future__ import annotations
from ..connectors import nasa_firms
from ..services.settings_service import get_api_key
from .base import ProviderContext, ProviderResult, ok, empty, needs_key, error
from ._wrap import connector_ctx


class WildfireProvider:
    id = "wildfire"
    title = "Active wildfire"
    requires_key = "firms"
    always_on = False

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        if not get_api_key(None, "firms"):
            return needs_key(self.id, self.title, "SUMMIT_SIGNAL_FIRMS_KEY")
        try:
            cout = nasa_firms.run(connector_ctx(ctx.latitude, ctx.longitude))
            n = cout.normalized or {}
            count = n.get("count") or 0
            if count == 0:
                return empty(self.id, self.title, "No active fire detections nearby (last 3 days)")
            nearest = (n.get("detections") or [{}])[0]
            return ok(self.id, self.title, data={
                "count": count,
                "nearest_miles": n.get("nearest_miles"),
                "nearest_confidence": nearest.get("confidence"),
            }, source_name="NASA FIRMS (VIIRS, last 3 days)",
               source_url="https://firms.modaps.eosdis.nasa.gov/map/")
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
