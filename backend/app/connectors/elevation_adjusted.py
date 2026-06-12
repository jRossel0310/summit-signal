"""Elevation-Adjusted Weather Module.

Not a remote source: it derives temperature estimates for user-defined
elevation bands from the NWS point forecast using a standard lapse-rate
approximation (~3.5 degF per 1,000 ft / 6.5 degC per km). Output is clearly
labeled as an estimate, never as an official forecast.

Runs after nws_weather and usgs_elevation; reads their results from ctx.shared.
"""
from __future__ import annotations
from .base import ConnectorContext, skipped, utcnow_iso
from ..schemas import ConnectorOutput

NAME = "elevation_adjusted"
SOURCE = "SummitSignal lapse-rate estimate (derived, not an official forecast)"
LAPSE_F_PER_1000FT = 3.5


def run(ctx: ConnectorContext) -> ConnectorOutput:
    nws = ctx.shared.get("nws_normalized")
    if not nws or not nws.get("periods"):
        return skipped(NAME, SOURCE, "No NWS forecast available to adjust")
    if ctx.elevation_ft is None:
        return skipped(NAME, SOURCE, "No base elevation available (USGS check failed)")

    base_ft = ctx.elevation_ft
    bands = dict(ctx.elevation_bands or {})

    # Sensible defaults from GPX route elevations when bands are not set
    gpx = ctx.shared.get("gpx_meta") or {}
    if not any(bands.get(k) is not None for k in ("trailhead_ft", "mid_ft", "high_ft")):
        if gpx.get("min_elevation_ft") is not None and gpx.get("max_elevation_ft") is not None:
            bands = {
                "trailhead_ft": gpx["min_elevation_ft"],
                "mid_ft": (gpx["min_elevation_ft"] + gpx["max_elevation_ft"]) / 2,
                "high_ft": gpx["max_elevation_ft"],
            }

    band_list = []
    for label, key in (("Trailhead", "trailhead_ft"), ("Mid-route", "mid_ft"),
                       ("High point / summit", "high_ft")):
        target = bands.get(key)
        if target is None:
            continue
        delta_ft = float(target) - base_ft
        delta_f = -(delta_ft / 1000.0) * LAPSE_F_PER_1000FT
        entry = {"label": label, "elevation_ft": round(float(target)),
                 "temp_offset_f": round(delta_f, 1), "periods": []}
        for p in nws["periods"][:8]:
            t = p.get("temperature_f")
            if t is None:
                continue
            entry["periods"].append({
                "name": p["name"],
                "estimated_temp_f": round(t + delta_f),
                "forecast_point_temp_f": t,
            })
        band_list.append(entry)

    freezing_band_note = None
    high = bands.get("high_ft")
    if high is not None and nws.get("low_f") is not None:
        est_low_at_high = nws["low_f"] - ((float(high) - base_ft) / 1000.0) * LAPSE_F_PER_1000FT
        freezing_band_note = {
            "estimated_overnight_low_at_high_point_f": round(est_low_at_high),
            "above_freezing_overnight": est_low_at_high > 32,
        }
        ctx.shared["est_low_at_high_f"] = est_low_at_high

    normalized = {
        "is_estimate": True,
        "method": f"Standard lapse rate ~{LAPSE_F_PER_1000FT} degF per 1,000 ft applied to the NWS point forecast",
        "base_elevation_ft": round(base_ft),
        "bands": band_list,
        "high_point_overnight": freezing_band_note,
        "warning": "Estimates only. Actual mountain temperatures vary with inversions, "
                   "wind, aspect, and weather pattern. Not an official forecast.",
    }
    return ConnectorOutput(
        connector_name=NAME,
        status="success" if band_list else "partial",
        source_name=SOURCE,
        source_url="",
        source_timestamp=utcnow_iso(),
        raw=None,
        normalized=normalized,
        error_message=None if band_list else "No elevation bands defined; set bands on the trip for estimates",
    )
