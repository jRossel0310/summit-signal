"""SlopeAspectProvider + pure slope/aspect math.

Map-shading slope/aspect is computed client-side in a worker; this module is the
unit-tested source of truth for the single-point value shown in the dashboard."""
from __future__ import annotations
import math
from ..connectors.base import http_client, utcnow_iso
from .base import ProviderContext, ProviderResult, ok, empty, error

OPEN_METEO_URL = "https://api.open-meteo.com/v1/elevation"
_SPACING_M = 50.0

# Slope buckets (avalanche-standard). Boundaries shared in spirit with the
# frontend terrainColors.ts; the two live in different languages.
_BUCKETS = [(0, 15, "0–15°"), (15, 25, "15–25°"), (25, 30, "25–30°"),
            (30, 35, "30–35°"), (35, 45, "35–45°"), (45, None, "45°+")]
_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compute_slope_aspect(center, north, east, south, west, spacing_m) -> tuple[float, float]:
    """Returns (slope_deg, aspect_deg) from 5 elevations (m) and the ground
    spacing (m). aspect_deg is the compass bearing of the downslope-faced
    direction: 0 = N, 90 = E, clockwise."""
    dzdx = (east - west) / (2.0 * spacing_m)
    dzdy = (north - south) / (2.0 * spacing_m)
    slope = math.degrees(math.atan(math.hypot(dzdx, dzdy)))
    if dzdx == 0 and dzdy == 0:
        return 0.0, 0.0
    aspect = (math.degrees(math.atan2(-dzdx, -dzdy)) + 360.0) % 360.0
    return slope, aspect


def slope_bucket_label(deg: float) -> str:
    for lo, hi, label in _BUCKETS:
        if deg >= lo and (hi is None or deg < hi):
            return label
    return _BUCKETS[-1][2]


def aspect_compass(deg: float) -> str:
    return _COMPASS[int((deg % 360) / 45.0 + 0.5) % 8]


class SlopeAspectProvider:
    id = "slope_aspect"
    title = "Slope & aspect"
    requires_key = None
    always_on = True

    def fetch(self, ctx: ProviderContext) -> ProviderResult:
        lat, lon = ctx.latitude, ctx.longitude
        dlat = _SPACING_M / 111320.0
        dlon = _SPACING_M / (111320.0 * max(0.1, math.cos(math.radians(lat))))
        # order: center, north, east, south, west
        lats = [lat, lat + dlat, lat, lat - dlat, lat]
        lons = [lon, lon, lon + dlon, lon, lon - dlon]
        try:
            with http_client() as client:
                r = client.get(OPEN_METEO_URL, params={
                    "latitude": ",".join(f"{v:.6f}" for v in lats),
                    "longitude": ",".join(f"{v:.6f}" for v in lons)})
                r.raise_for_status()
                elevs = r.json().get("elevation") or []
                if len(elevs) < 5 or any(e is None for e in elevs[:5]):
                    return empty(self.id, self.title, "No elevation data at this point")
                c, n, e, s, w = (float(x) for x in elevs[:5])
                slope, aspect = compute_slope_aspect(c, n, e, s, w, _SPACING_M)
                return ok(self.id, self.title, data={
                    "slope_deg": round(slope, 1),
                    "aspect_deg": round(aspect, 1),
                    "aspect_compass": aspect_compass(aspect),
                    "slope_bucket": slope_bucket_label(slope),
                }, source_name="Open-Meteo elevation (5-sample slope estimate)",
                   source_url=OPEN_METEO_URL, source_timestamp=utcnow_iso())
        except Exception as e:  # noqa: BLE001
            return error(self.id, self.title, str(e))
