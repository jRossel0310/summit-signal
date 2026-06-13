"""AI summary module (rule-based only).

Deterministic markdown built from connector results and risk flags.
Ends with the required disclaimer.
"""
from __future__ import annotations

DISCLAIMER = ("This tool highlights planning concerns from available sources. "
              "It does not determine whether a trip is safe.")


def summarize(trip: dict, flags: list[dict], outputs: list[dict],
              checklist: list[str], settings: dict) -> tuple[str, str]:
    """Returns (markdown, generator_name). Rule-based only."""
    return _rule_based(trip, flags, outputs, checklist), "rule_based"


# ---------------- rule-based ----------------

def _section(flags, severity):
    rows = [f for f in flags if f["severity"] == severity]
    if not rows:
        return "- None identified from the sources checked.\n"
    out = ""
    for f in rows:
        out += f"- **{f['title']}**: {f['description']}"
        if f.get("source_url"):
            out += f" ([source]({f['source_url']}))"
        out += "\n"
    return out


def _rule_based(trip, flags, outputs, checklist) -> str:
    by = {o["connector_name"]: o for o in outputs}
    md = [f"## Trip overview",
          f"**{trip['name']}** - {trip.get('location_name') or 'selected point'} "
          f"({trip['latitude']:.4f}, {trip['longitude']:.4f}), "
          f"{trip['start_date']} to {trip['end_date']}, "
          f"trip type: {trip['trip_type']}."]

    elev = (by.get("usgs_elevation") or {}).get("normalized") or {}
    if elev.get("elevation_ft"):
        md.append(f"Selected point elevation: {elev['elevation_ft']:.0f} ft "
                  f"({elev['elevation_m']:.0f} m).")

    md.append("\n## Major concerns\n" + _section(flags, "major"))
    md.append("## Moderate concerns\n" + _section(flags, "moderate"))

    # Weather interpretation
    wx = (by.get("nws_weather") or {}).get("normalized") or {}
    md.append("## Weather interpretation")
    if wx.get("periods"):
        md.append(f"Forecast point range roughly {wx.get('low_f','?')}F to "
                  f"{wx.get('high_f','?')}F, max winds about {wx.get('max_wind_mph',0):.0f} mph, "
                  f"max precipitation chance {wx.get('max_precip_chance',0):.0f}%.")
        firsts = wx["periods"][:6]
        for p in firsts:
            md.append(f"- {p['name']}: {p['temperature_f']}F, {p['wind_speed'] or 'calm'}, "
                      f"{p['precip_chance']}% precip, {p['short_forecast']}")
    else:
        md.append("No NWS forecast data was retrieved; check forecast.weather.gov manually.")

    adj = (by.get("elevation_adjusted") or {}).get("normalized") or {}
    if adj.get("bands"):
        md.append("\nElevation-adjusted estimates (lapse-rate approximation, **not** an "
                  "official forecast):")
        for b in adj["bands"]:
            off = b["temp_offset_f"]
            md.append(f"- {b['label']} ({b['elevation_ft']} ft): about {off:+.0f}F vs. the "
                      "forecast point.")

    disc = (by.get("weather_discussion") or {}).get("normalized") or {}
    if disc.get("highlights"):
        md.append("\nForecast discussion highlights "
                  f"(NWS {disc.get('office','')} AFD):")
        for topic, hits in disc["highlights"].items():
            md.append(f"- *{topic.replace('_',' ').title()}*: {hits[0]}")

    # Fire / smoke
    md.append("\n## Fire and smoke")
    firms = (by.get("nasa_firms") or {})
    if firms.get("status") == "success":
        n = firms.get("normalized") or {}
        if n.get("count"):
            md.append(f"{n['count']} active fire detection(s) in the search area in the last "
                      f"{n.get('search_days')} days; nearest ~{n.get('nearest_miles')} mi.")
        else:
            md.append("No active satellite fire detections in the search area.")
    else:
        md.append(f"Active fire detections: {firms.get('error_message') or 'not checked'}.")
    per = (by.get("nifc_wfigs") or {})
    if per.get("status") == "success":
        n = per.get("normalized") or {}
        if n.get("selected_point_inside_perimeter"):
            md.append("The selected location is **inside** a mapped fire perimeter.")
        elif n.get("count"):
            md.append(f"{n['count']} mapped fire perimeter(s) intersect the search area.")
        else:
            md.append("No current fire perimeters intersect the search area.")
    air = (by.get("airnow") or {})
    if air.get("status") in ("success", "partial"):
        aqi = ((air.get("normalized") or {}).get("max_aqi"))
        md.append(f"Current AQI near the location: {aqi if aqi is not None else 'no nearby station'} "
                  "(AirNow preliminary/unvalidated data).")

    # Official alerts
    md.append("\n## Official alerts")
    nps = (by.get("nps_alerts") or {})
    npsn = nps.get("normalized") or {}
    if npsn.get("applicable") and npsn.get("alerts"):
        for a in npsn["alerts"][:8]:
            md.append(f"- [{a.get('category')}] {a.get('park')}: {a.get('title')}")
    elif npsn.get("applicable") is False:
        md.append("Location is not near a National Park Service unit (NPS alerts not applicable).")
    else:
        md.append(f"NPS alerts: {nps.get('error_message') or 'not checked'}.")
    if wx.get("alerts"):
        for a in wx["alerts"]:
            md.append(f"- [NWS {a.get('severity')}] {a.get('event')}: {a.get('headline')}")

    # Avalanche / snow
    av = (by.get("avalanche") or {})
    avn = av.get("normalized") or {}
    if avn:
        md.append("\n## Avalanche / snow")
        zone = avn.get("zone") or {}
        if zone:
            md.append(f"Forecast coverage: {zone.get('center') or zone.get('zone_name') or 'see link'}"
                      + (f" - {zone.get('forecast_link')}" if zone.get("forecast_link") else ""))
        if avn.get("manual_check_required"):
            md.append("**Manual avalanche forecast check required** for this trip type/terrain.")

    # Data gaps
    md.append("\n## Data gaps")
    gaps = [f for f in flags if f["category"] == "data_gap"]
    if gaps:
        for g in gaps:
            md.append(f"- {g['title']}: {g['description']}")
    else:
        md.append("- All enabled sources returned data.")

    # Checklist
    md.append("\n## Manual verification checklist")
    for item in checklist:
        md.append(f"- [ ] {item}")

    # Sources
    md.append("\n## Sources")
    for o in outputs:
        if o.get("source_name"):
            line = f"- {o['source_name']} - status: {o['status']}"
            if o.get("source_timestamp"):
                line += f", source time: {o['source_timestamp']}"
            if o.get("source_url"):
                line += f" - {o['source_url']}"
            md.append(line)

    md.append(f"\n---\n*{DISCLAIMER}*")
    return "\n".join(md)
