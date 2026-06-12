"""Risk engine.

Turns normalized connector outputs into risk flags and an overall concern
status. SummitSignal never makes go/no-go calls — statuses are limited to the
five approved phrases and flags describe what was found, where it came from,
and how confident the source signal is.
"""
from __future__ import annotations
import datetime as dt
from ..schemas import ConnectorOutput

MAJOR_ALERT_EVENTS = [
    "high wind warning", "high wind watch", "winter storm warning", "winter storm watch",
    "blizzard warning", "excessive heat warning", "flash flood warning", "flash flood watch",
    "tornado", "severe thunderstorm warning", "red flag warning", "avalanche warning",
    "ice storm warning", "fire weather warning",
]
CLOSURE_WORDS = ["closure", "closed", "danger", "evacuat", "fire restriction",
                 "road closed", "trail closed", "rescue", "prohibited"]


def flag(severity, category, title, description, source_connector, source_url="",
         confidence="medium") -> dict:
    return {
        "severity": severity, "category": category, "title": title,
        "description": description, "source_connector": source_connector,
        "source_url": source_url, "confidence": confidence,
    }


def evaluate(outputs: list[ConnectorOutput], settings: dict, trip_type: str,
             enabled: dict) -> tuple[list[dict], str, float]:
    """Returns (flags, overall_concern_status, data_completeness_score)."""
    flags: list[dict] = []
    by_name = {o.connector_name: o for o in outputs}

    flags += _weather_flags(by_name.get("nws_weather"), settings, trip_type)
    flags += _elevation_flags(by_name.get("elevation_adjusted"), trip_type)
    flags += _firms_flags(by_name.get("nasa_firms"), settings)
    flags += _perimeter_flags(by_name.get("nifc_wfigs"))
    flags += _airnow_flags(by_name.get("airnow"), settings)
    flags += _nps_flags(by_name.get("nps_alerts"))
    flags += _avalanche_flags(by_name.get("avalanche"), trip_type)

    # Data gaps from connector status
    for o in outputs:
        if o.status == "failed":
            flags.append(flag(
                "unknown", "data_gap", f"Source check failed: {o.source_name or o.connector_name}",
                f"{o.error_message or 'Unknown error'}. Check this source manually before the trip.",
                o.connector_name, o.source_url, "high"))
        elif o.status == "skipped" and "API key" in (o.error_message or ""):
            flags.append(flag(
                "unknown", "data_gap", f"API key needed: {o.connector_name}",
                o.error_message or "", o.connector_name, o.source_url, "high"))
        elif o.status == "skipped":
            flags.append(flag(
                "unknown", "data_gap", f"Check skipped: {o.connector_name}",
                o.error_message or "Connector did not run.", o.connector_name,
                o.source_url, "medium"))

    # Stale source data
    stale_hours = float(settings.get("stale_hours", 24))
    for o in outputs:
        ts = _parse_ts(o.source_timestamp)
        if ts and (dt.datetime.now(dt.timezone.utc) - ts).total_seconds() > stale_hours * 3600:
            flags.append(flag(
                "unknown", "data_gap", f"Stale data: {o.connector_name}",
                f"Source timestamp is older than {stale_hours:.0f} hours "
                f"({o.source_timestamp}). Re-check closer to your trip.",
                o.connector_name, o.source_url, "medium"))

    # Completeness: success=1, partial=0.5 over enabled connectors that ran
    ran = [o for o in outputs]
    score_points = sum(1.0 if o.status == "success" else 0.5 if o.status == "partial" else 0.0
                       for o in ran)
    completeness = round(score_points / len(ran), 2) if ran else 0.0

    overall = _overall_status(flags, outputs, completeness)
    return flags, overall, completeness


def _overall_status(flags, outputs, completeness) -> str:
    core = [o for o in outputs if o.connector_name in ("nws_weather", "usgs_elevation")]
    if core and all(o.status == "failed" for o in core):
        return "Source check failed"
    severities = {f["severity"] for f in flags}
    if "major" in severities:
        return "Major concerns found"
    if "moderate" in severities:
        return "Some concerns found"
    if completeness < 0.7 or "unknown" in severities:
        return "Data incomplete"
    return "No major concerns found"


def _parse_ts(value):
    if not value:
        return None
    try:
        ts = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


# ---------------- per-connector rules ----------------

def _weather_flags(o, settings, trip_type):
    if not o or o.status in ("failed", "skipped") or not o.normalized:
        return []
    n = o.normalized
    flags = []
    for a in n.get("alerts", []):
        event = (a.get("event") or "").lower()
        is_major = any(m in event for m in MAJOR_ALERT_EVENTS) or \
            (a.get("severity") in ("Extreme", "Severe"))
        flags.append(flag(
            "major" if is_major else "moderate", "weather",
            f"NWS alert: {a.get('event')}",
            a.get("headline") or (a.get("description") or "")[:300],
            "nws_weather", a.get("url") or o.source_url, "high"))
    gust_major = float(settings.get("wind_gust_major_mph", 50))
    gust_mod = float(settings.get("wind_gust_moderate_mph", 30))
    wind = n.get("max_wind_mph", 0)
    if wind >= gust_major:
        flags.append(flag("major", "weather", f"Very strong winds forecast (up to {wind:.0f} mph)",
                          "Forecast wind speeds reach the major-concern threshold. "
                          "Exposed ridges and summits will be significantly windier.",
                          "nws_weather", o.source_url, "high"))
    elif wind >= gust_mod:
        flags.append(flag("moderate", "weather", f"Strong winds forecast (up to {wind:.0f} mph)",
                          "Plan for wind on exposed terrain; verify ridge-top forecasts.",
                          "nws_weather", o.source_url, "high"))
    pp = n.get("max_precip_chance", 0)
    if pp >= float(settings.get("precip_prob_moderate", 60)):
        flags.append(flag("moderate", "weather", f"High precipitation probability ({pp:.0f}%)",
                          "Significant chance of precipitation during the forecast window.",
                          "nws_weather", o.source_url, "high"))
    if n.get("thunder_mentioned"):
        flags.append(flag("moderate", "weather", "Thunderstorms in forecast",
                          "Thunderstorms are mentioned in the forecast. Plan exposure and "
                          "summit timing accordingly.", "nws_weather", o.source_url, "high"))
    low = n.get("low_f")
    if low is not None and low <= float(settings.get("cold_low_f", 10)):
        flags.append(flag("moderate", "weather", f"Very cold temperatures (low {low:.0f}F at forecast point)",
                          "Lows reach the cold-concern threshold at the forecast point; "
                          "higher elevations will be colder.", "nws_weather", o.source_url, "high"))
    if n.get("snow_mentioned") and trip_type != "mountaineering":
        flags.append(flag("info", "snow", "Snow mentioned in forecast",
                          "Snow appears in the forecast text. Check trail and pass conditions.",
                          "nws_weather", o.source_url, "medium"))
    return flags


def _elevation_flags(o, trip_type):
    if not o or not o.normalized:
        return []
    n = o.normalized
    flags = []
    hp = n.get("high_point_overnight")
    if hp and trip_type in ("mountaineering",) and hp.get("above_freezing_overnight"):
        flags.append(flag(
            "moderate", "snow",
            "Estimated overnight low above freezing at high point",
            f"Lapse-rate estimate puts the overnight low near "
            f"{hp.get('estimated_overnight_low_at_high_point_f')}F at the high point. "
            "Poor overnight refreeze affects snow bridges and glacier travel. "
            "This is an estimate — verify with the official forecast discussion.",
            "elevation_adjusted", "", "low"))
    if n.get("is_estimate") and n.get("bands"):
        flags.append(flag(
            "info", "weather", "Elevation temperatures are lapse-rate estimates",
            n.get("warning", ""), "elevation_adjusted", "", "low"))
    return flags


def _firms_flags(o, settings):
    if not o or o.status in ("failed", "skipped") or not o.normalized:
        return []
    n = o.normalized
    flags = []
    nearest = n.get("nearest_miles")
    count = n.get("count", 0)
    radius = float(settings.get("fire_radius_miles", 30))
    if nearest is not None and nearest <= 5:
        flags.append(flag("major", "fire",
                          f"Active fire detection {nearest} mi from location",
                          f"{count} satellite detections in the last {n.get('search_days')} days "
                          "within the search area; the nearest is very close to your "
                          "location/route. Verify incident status with land managers.",
                          "nasa_firms", o.source_url, "medium"))
    elif count > 0:
        flags.append(flag("moderate", "fire",
                          f"{count} active fire detections within ~{radius:.0f} mi",
                          f"Nearest detection ~{nearest} mi away. Satellite detections can "
                          "include prescribed burns and false positives; verify before travel.",
                          "nasa_firms", o.source_url, "medium"))
    return flags


def _perimeter_flags(o):
    if not o or o.status in ("failed", "skipped") or not o.normalized:
        return []
    n = o.normalized
    flags = []
    if n.get("selected_point_inside_perimeter"):
        flags.append(flag("major", "fire", "Location is inside a mapped fire perimeter",
                          "The selected point or route falls inside a current interagency "
                          "fire perimeter. Expect closures; contact the managing agency.",
                          "nifc_wfigs", o.source_url, "high"))
    elif n.get("count", 0) > 0:
        nearest = min((p.get("approx_distance_miles") or 9999) for p in n.get("perimeters", []))
        flags.append(flag("moderate", "fire",
                          f"{n['count']} fire perimeter(s) near the search area",
                          f"Nearest perimeter centroid ~{nearest} mi away. Perimeters can be "
                          "recent or historic-season; check incident status and closures.",
                          "nifc_wfigs", o.source_url, "medium"))
    return flags


def _airnow_flags(o, settings):
    if not o or o.status in ("failed", "skipped") or not o.normalized:
        return []
    n = o.normalized
    aqi = n.get("max_aqi")
    if aqi is None:
        return []
    major_t = int(settings.get("aqi_major_threshold", 151))
    mod_t = int(settings.get("aqi_moderate_threshold", 101))
    if aqi >= major_t:
        return [flag("major", "smoke", f"Air quality unhealthy (AQI {aqi})",
                     "Current AQI is at or above the unhealthy threshold. "
                     "AirNow current observations are preliminary/unvalidated.",
                     "airnow", o.source_url, "medium")]
    if aqi >= mod_t:
        return [flag("moderate", "smoke", f"Air quality unhealthy for sensitive groups (AQI {aqi})",
                     "AirNow current observations are preliminary/unvalidated.",
                     "airnow", o.source_url, "medium")]
    return []


def _nps_flags(o):
    if not o or o.status in ("failed", "skipped") or not o.normalized:
        return []
    n = o.normalized
    if not n.get("applicable"):
        return []
    flags = []
    for a in n.get("alerts", []):
        text = f"{a.get('category','')} {a.get('title','')} {a.get('description','')}".lower()
        category = (a.get("category") or "").lower()
        if category in ("danger", "closure") or any(w in text for w in CLOSURE_WORDS):
            sev = "major"
        elif category == "caution":
            sev = "moderate"
        else:
            sev = "info"
        flags.append(flag(sev, "official_alert",
                          f"NPS {a.get('category','alert')}: {a.get('title','')}".strip(),
                          f"{a.get('park','')}: {(a.get('description') or '')[:400]}",
                          "nps_alerts", a.get("url") or o.source_url, "high"))
    return flags


def _avalanche_flags(o, trip_type):
    if not o or not o.normalized:
        if trip_type == "mountaineering":
            return [flag("unknown", "avalanche", "Avalanche region unknown",
                         "Could not determine avalanche forecast coverage for this "
                         "mountaineering/glacier trip. Manual avalanche forecast check required.",
                         "avalanche", "https://avalanche.org/", "high")]
        return []
    n = o.normalized
    flags = []
    zone = n.get("zone") or {}
    if n.get("manual_check_required"):
        link = zone.get("forecast_link") or "https://avalanche.org/"
        center = zone.get("center") or "your regional avalanche center"
        flags.append(flag("moderate" if trip_type == "mountaineering" else "info",
                          "avalanche", "Manual avalanche forecast check required",
                          f"Read the current forecast from {center} before travel. "
                          "SummitSignal links to forecasts but does not interpret avalanche danger.",
                          "avalanche", link, "high"))
    if n.get("in_forecast_zone") is False and trip_type == "mountaineering":
        flags.append(flag("unknown", "avalanche", "No professional avalanche forecast zone found",
                          "The selected point is outside known avalanche.org forecast zones. "
                          "Conditions assessment will rely on your own observations.",
                          "avalanche", "https://avalanche.org/", "medium"))
    return flags


def build_manual_checklist(outputs: list[ConnectorOutput], trip_type: str) -> list[str]:
    by_name = {o.connector_name: o for o in outputs}
    items = [
        "Confirm road and trailhead access with the managing agency (USFS/BLM/NPS/state).",
        "Check permit and quota requirements for your route and dates.",
        "Re-run this condition check within 24 hours of departure — forecasts change.",
        "Leave a trip plan with an emergency contact.",
    ]
    av = by_name.get("avalanche")
    if trip_type == "mountaineering" or (av and (av.normalized or {}).get("winter_relevant")):
        items.insert(0, "Read the full avalanche forecast from the regional center, including "
                        "the discussion, not just the danger rating.")
        items.append("Check recent route conditions (ranger reports, climbing ranger blogs, "
                     "guide services) for glacier/route status.")
    if by_name.get("nasa_firms") and by_name["nasa_firms"].status == "skipped":
        items.append("Check fire activity manually at inciweb.wildfire.gov and the FIRMS map.")
    if by_name.get("airnow") and by_name["airnow"].status == "skipped":
        items.append("Check smoke/air quality manually at fire.airnow.gov.")
    if trip_type in ("backpacking", "mountaineering"):
        items.append("Verify water source status for your route where relevant.")
    return items
