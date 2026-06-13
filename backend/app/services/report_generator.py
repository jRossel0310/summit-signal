"""Printable report generator. Renders a standalone HTML planning summary for a
trip's latest (or chosen) condition check, with print-friendly CSS."""
from __future__ import annotations
import datetime as dt
import html
import json

from .. import models

DISCLAIMER = ("This tool highlights planning concerns from available sources. "
              "It does not determine whether a trip is safe.")

SEV_LABEL = {"major": "MAJOR", "moderate": "MODERATE", "info": "INFO", "unknown": "DATA GAP"}

CSS = """
:root { --ink:#1b1f23; --rule:#c9c4b8; --major:#b3261e; --mod:#9a6700; --info:#1f6f64; --gap:#5f6368; }
* { box-sizing: border-box; }
body { font-family: Georgia, 'Times New Roman', serif; color: var(--ink); margin: 0;
       padding: 32px 40px; max-width: 880px; margin-inline: auto; line-height: 1.45; }
h1 { font-size: 26px; margin: 0 0 2px; letter-spacing: .2px; }
h2 { font-size: 15px; text-transform: uppercase; letter-spacing: .12em; border-bottom: 1.5px solid var(--ink);
     padding-bottom: 4px; margin: 26px 0 10px; font-family: Arial, Helvetica, sans-serif; }
.meta, .src, small { font-family: Arial, Helvetica, sans-serif; }
.meta { color:#444; font-size: 13px; margin-bottom: 14px; }
.status { display:inline-block; font-family: Arial, sans-serif; font-weight: 700; font-size: 14px;
          border: 2px solid var(--ink); padding: 6px 12px; margin: 6px 0 0; }
table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
td, th { border-bottom: 1px solid var(--rule); padding: 6px 8px 6px 0; text-align: left; vertical-align: top; }
th { font-family: Arial, sans-serif; font-size: 11px; text-transform: uppercase; letter-spacing:.08em; color:#555; }
.badge { font-family: Arial, sans-serif; font-size: 10.5px; font-weight:700; letter-spacing:.06em;
         padding: 2px 6px; border: 1.5px solid; white-space: nowrap; }
.badge.major { color: var(--major); border-color: var(--major); }
.badge.moderate { color: var(--mod); border-color: var(--mod); }
.badge.info { color: var(--info); border-color: var(--info); }
.badge.unknown { color: var(--gap); border-color: var(--gap); }
ul { padding-left: 20px; margin: 6px 0; }
li { margin: 3px 0; }
.checklist li { list-style: none; margin: 6px 0; }
.checklist li::before { content: "\\2610  "; font-size: 15px; }
.src { font-size: 12px; color: #444; }
.disclaimer { margin-top: 28px; border: 1.5px solid var(--ink); padding: 10px 14px;
              font-family: Arial, sans-serif; font-size: 12.5px; }
a { color: inherit; }
@media print { body { padding: 0; } .noprint { display: none; } h2 { break-after: avoid; } }
.noprint { font-family: Arial, sans-serif; margin-bottom: 18px; }
.noprint button { font-size: 14px; padding: 8px 16px; cursor: pointer; }
"""


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def generate_report_html(trip: models.Trip, check: models.ConditionCheck | None) -> str:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = [f"<!doctype html><html><head><meta charset='utf-8'>"
             f"<title>SummitSignal report - {_e(trip.name)}</title><style>{CSS}</style></head><body>"]
    parts.append("<div class='noprint'><button onclick='window.print()'>Print this report</button></div>")
    parts.append(f"<h1>SummitSignal planning report</h1>")
    parts.append(f"<div class='meta'>Generated {now} (local) &middot; "
                 f"All data retrieved by SummitSignal local agent</div>")

    parts.append("<h2>Trip</h2>")
    route_line = ""
    gpx = trip.gpx_route
    if gpx:
        length = gpx.length_miles if gpx.length_miles is not None else "?"
        lo = gpx.min_elevation_ft if gpx.min_elevation_ft is not None else "?"
        hi = gpx.max_elevation_ft if gpx.max_elevation_ft is not None else "?"
        route_line = (f"<tr><th>Route (GPX)</th><td>{_e(gpx.filename)} - "
                      f"~{length} mi, {lo}–{hi} ft</td></tr>")
    parts.append(
        "<table>"
        f"<tr><th>Name</th><td>{_e(trip.name)}</td></tr>"
        f"<tr><th>Location</th><td>{_e(trip.location_name)} "
        f"({trip.latitude:.4f}, {trip.longitude:.4f})</td></tr>"
        f"<tr><th>Dates</th><td>{_e(trip.start_date)} to {_e(trip.end_date)}</td></tr>"
        f"<tr><th>Trip type</th><td>{_e(trip.trip_type)}</td></tr>"
        f"{route_line}"
        f"<tr><th>Notes</th><td>{_e(trip.notes) or '-'}</td></tr>"
        "</table>")

    if check is None:
        parts.append("<p>No condition check has been run for this trip yet. "
                     "Run a condition check in SummitSignal, then print this report.</p>")
        parts.append(f"<div class='disclaimer'>{DISCLAIMER}</div></body></html>")
        return "".join(parts)

    parts.append("<h2>Overall status</h2>")
    parts.append(f"<div class='status'>{_e(check.overall_concern_status or 'Unknown')}</div>")
    parts.append(f"<div class='meta'>Checked {check.completed_at or check.started_at} UTC &middot; "
                 f"data completeness {int((check.data_completeness_score or 0)*100)}%</div>")

    flags = sorted(check.risk_flags,
                   key=lambda f: ["major", "moderate", "unknown", "info"].index(f.severity)
                   if f.severity in ("major", "moderate", "unknown", "info") else 9)
    for sev, heading in (("major", "Major concerns"), ("moderate", "Moderate concerns")):
        rows = [f for f in flags if f.severity == sev]
        parts.append(f"<h2>{heading}</h2>")
        if not rows:
            parts.append("<p>None identified from the sources checked.</p>")
        else:
            parts.append("<ul>")
            for f in rows:
                link = f" <span class='src'>(<a href='{_e(f.source_url)}'>source</a>)</span>" if f.source_url else ""
                parts.append(f"<li><span class='badge {f.severity}'>{SEV_LABEL[f.severity]}</span> "
                             f"<strong>{_e(f.title)}</strong>: {_e(f.description)}{link}</li>")
            parts.append("</ul>")

    results = {r.connector_name: r for r in check.connector_results}

    # Weather by day
    parts.append("<h2>Weather by period (NWS forecast point)</h2>")
    wx = _norm(results.get("nws_weather"))
    if wx.get("periods"):
        parts.append("<table><tr><th>Period</th><th>Temp</th><th>Wind</th><th>Precip</th><th>Forecast</th></tr>")
        for p in wx["periods"][:14]:
            parts.append(
                f"<tr><td>{_e(p.get('name', ''))}</td>"
                f"<td>{_e(p.get('temperature_f', '?'))}F</td>"
                f"<td>{_e(p.get('wind_speed', '-'))}</td>"
                f"<td>{_e(p.get('precip_chance', '-'))}%</td>"
                f"<td>{_e(p.get('short_forecast', ''))}</td></tr>")
        parts.append("</table>")
    else:
        parts.append("<p>No forecast data retrieved.</p>")

    # Elevation notes
    parts.append("<h2>Elevation notes</h2>")
    elev = _norm(results.get("usgs_elevation"))
    adj = _norm(results.get("elevation_adjusted"))
    if elev:
        parts.append(f"<p>Selected point elevation: {elev.get('elevation_ft','?')} ft "
                     f"({elev.get('elevation_m','?')} m).</p>")
    if adj.get("bands"):
        parts.append("<ul>")
        for b in adj["bands"]:
            off = b.get("temp_offset_f")
            off_str = "?" if off is None else f"{off:+.0f}"
            parts.append(f"<li>{_e(b.get('label', ''))} ({b.get('elevation_ft', '?')} ft): about "
                         f"{off_str}F vs. the forecast point (estimate).</li>")
        parts.append("</ul>")
        parts.append(f"<p class='src'>{_e(adj.get('warning',''))}</p>")

    # Fire / smoke
    parts.append("<h2>Fire and smoke</h2><ul>")
    firms = _norm(results.get("nasa_firms"))
    if firms:
        parts.append(f"<li>Active fire detections (last {firms.get('search_days','?')} days): "
                     f"{firms.get('count',0)}; nearest ~{firms.get('nearest_miles','-')} mi.</li>")
    else:
        parts.append(f"<li>Active fire detections: {_e(_err(results.get('nasa_firms')))}</li>")
    per = _norm(results.get("nifc_wfigs"))
    if per:
        inside = "inside a mapped perimeter" if per.get("selected_point_inside_perimeter") else \
                 f"{per.get('count',0)} perimeter(s) in the search area"
        parts.append(f"<li>Fire perimeters: {inside}.</li>")
    air = _norm(results.get("airnow"))
    if air:
        parts.append(f"<li>AQI: {air.get('max_aqi','no nearby station')} "
                     "(AirNow preliminary/unvalidated).</li>")
    else:
        parts.append(f"<li>Air quality: {_e(_err(results.get('airnow')))}</li>")
    parts.append("</ul>")

    # Official alerts
    parts.append("<h2>Official alerts</h2><ul>")
    any_alert = False
    for a in wx.get("alerts", []):
        any_alert = True
        parts.append(f"<li>[NWS {_e(a.get('severity'))}] {_e(a.get('event'))}: {_e(a.get('headline'))}</li>")
    nps = _norm(results.get("nps_alerts"))
    for a in nps.get("alerts", []):
        any_alert = True
        parts.append(f"<li>[NPS {_e(a.get('category'))}] {_e(a.get('park'))}: {_e(a.get('title'))}</li>")
    if nps.get("applicable") is False:
        parts.append("<li>NPS alerts: not applicable (not near an NPS unit).</li>")
        any_alert = True
    if not any_alert:
        parts.append("<li>No active official alerts retrieved.</li>")
    parts.append("</ul>")

    # Avalanche
    av = _norm(results.get("avalanche"))
    parts.append("<h2>Avalanche / snow</h2>")
    if av:
        zone = av.get("zone") or {}
        if zone:
            parts.append(f"<p>Coverage: {_e(zone.get('center') or zone.get('zone_name') or 'see avalanche.org')}"
                         + (f" - <a href='{_e(zone.get('forecast_link'))}'>{_e(zone.get('forecast_link'))}</a>"
                            if zone.get("forecast_link") else "") + "</p>")
        if av.get("manual_check_required"):
            parts.append("<p><strong>Manual avalanche forecast check required.</strong> "
                         "Read the full regional forecast before travel.</p>")
        else:
            parts.append("<p>No avalanche-specific manual check triggered for this trip "
                         "type/terrain; verify if seasonal snow is possible.</p>")
    else:
        parts.append(f"<p>{_e(_err(results.get('avalanche')))}</p>")

    # Manual checklist (recreate from summary text section if present)
    parts.append("<h2>Manual verification checklist</h2><ul class='checklist'>")
    for line in (check.summary_text or "").splitlines():
        if line.strip().startswith("- [ ]"):
            parts.append(f"<li>{_e(line.strip()[5:].strip())}</li>")
    parts.append("</ul>")

    # Sources
    parts.append("<h2>Sources and timestamps</h2>")
    parts.append("<table><tr><th>Source</th><th>Status</th><th>Source time</th><th>Retrieved</th><th>Link</th></tr>")
    for r in check.connector_results:
        link = f"<a href='{_e(r.source_url)}'>link</a>" if r.source_url else "-"
        parts.append(f"<tr><td>{_e(r.source_name or r.connector_name)}</td><td>{_e(r.status)}</td>"
                     f"<td class='src'>{_e(r.source_timestamp or '-')}</td>"
                     f"<td class='src'>{_e(r.retrieved_at)}</td><td>{link}</td></tr>")
    parts.append("</table>")

    parts.append(f"<div class='disclaimer'>{DISCLAIMER}</div>")
    parts.append("</body></html>")
    return "".join(parts)


def _norm(result: models.ConnectorResult | None) -> dict:
    if result is None or not result.normalized_json:
        return {}
    try:
        return json.loads(result.normalized_json)
    except json.JSONDecodeError:
        return {}


def _err(result: models.ConnectorResult | None) -> str:
    if result is None:
        return "not checked"
    return result.error_message or f"status: {result.status}"
