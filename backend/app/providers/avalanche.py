"""Avalanche point provider — your zone's danger + center (wraps avalanche)."""
from __future__ import annotations
from ..connectors import avalanche
from .base import ProviderContext, ProviderResult, ok, empty, error
from ._wrap import connector_ctx


class AvalancheProvider:
    id = "avalanche"
    title = "Avalanche zone"
    requires_key = None
    always_on = False

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        try:
            cout = avalanche.run(connector_ctx(ctx.latitude, ctx.longitude))
            n = cout.normalized or {}
            zone = n.get("zone")
            if not n.get("in_forecast_zone") or not zone:
                return empty(self.id, self.title,
                             "Not inside a mapped avalanche forecast zone")
            return ok(self.id, self.title, data={
                "zone_name": zone.get("zone_name"),
                "danger": zone.get("current_danger"),
                "center": zone.get("center"),
            }, source_name="Avalanche.org forecast zones",
               source_url=zone.get("forecast_link") or "https://avalanche.org/")
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
