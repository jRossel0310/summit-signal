"""SlopeAspectProvider + pure slope/aspect math.

Map-shading slope/aspect is computed client-side in a worker; this module is the
unit-tested source of truth for the single-point value shown in the dashboard."""
from __future__ import annotations
import math

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
