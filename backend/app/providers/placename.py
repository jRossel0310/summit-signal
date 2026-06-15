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
