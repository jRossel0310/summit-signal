"""NWS Weather Connector.

Flow: points -> grid metadata -> daily forecast + hourly forecast + active alerts.
Normalized output includes daily periods (temps, wind, precip chance, snow
mentions), hourly sample, alerts, and the forecast office (shared with the
weather_discussion connector).
Source: api.weather.gov (no API key required).
"""
from __future__ import annotations
import re
from .base import ConnectorContext, http_client, failed, utcnow_iso
from ..schemas import ConnectorOutput

NAME = "nws_weather"
SOURCE = "National Weather Service (api.weather.gov)"


def _parse_wind_mph(wind_speed: str) -> float:
    """'10 to 20 mph' -> 20.0 ; '15 mph' -> 15.0"""
    if not wind_speed:
        return 0.0
    nums = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", wind_speed)]
    return max(nums) if nums else 0.0


def run(ctx: ConnectorContext) -> ConnectorOutput:
    points_url = f"https://api.weather.gov/points/{ctx.latitude:.4f},{ctx.longitude:.4f}"
    try:
        with http_client() as client:
            points = client.get(points_url)
            points.raise_for_status()
            pj = points.json()
            props = pj.get("properties", {})
            office = props.get("gridId") or props.get("cwa")
            forecast_url = props.get("forecast")
            hourly_url = props.get("forecastHourly")
            ctx.shared["nws_office"] = office
            ctx.shared["nws_zone"] = (props.get("forecastZone") or "").rsplit("/", 1)[-1]
            rel = (props.get("relativeLocation") or {}).get("properties") or {}
            if rel.get("state"):
                ctx.shared["nws_state"] = rel["state"]

            raw = {"points": props}
            normalized: dict = {"office": office, "periods": [], "hourly_sample": [], "alerts": []}
            status = "success"
            problems = []

            # Daily forecast
            if forecast_url:
                try:
                    fr = client.get(forecast_url)
                    fr.raise_for_status()
                    fj = fr.json()
                    raw["forecast_updated"] = fj.get("properties", {}).get("updateTime")
                    for p in fj.get("properties", {}).get("periods", []):
                        pop = (p.get("probabilityOfPrecipitation") or {}).get("value")
                        normalized["periods"].append({
                            "name": p.get("name"),
                            "start_time": p.get("startTime"),
                            "is_daytime": p.get("isDaytime"),
                            "temperature_f": p.get("temperature"),
                            "wind_speed": p.get("windSpeed"),
                            "wind_max_mph": _parse_wind_mph(p.get("windSpeed", "")),
                            "wind_direction": p.get("windDirection"),
                            "precip_chance": pop if pop is not None else 0,
                            "short_forecast": p.get("shortForecast"),
                            "detailed_forecast": p.get("detailedForecast"),
                        })
                except Exception as e:  # noqa: BLE001
                    problems.append(f"daily forecast: {e}")
            else:
                problems.append("no forecast URL for this point")

            # Hourly forecast (sampled every 3 hours to keep payload small)
            if hourly_url:
                try:
                    hr = client.get(hourly_url)
                    hr.raise_for_status()
                    hj = hr.json()
                    hours = hj.get("properties", {}).get("periods", [])[:72]
                    for p in hours[::3]:
                        pop = (p.get("probabilityOfPrecipitation") or {}).get("value")
                        normalized["hourly_sample"].append({
                            "time": p.get("startTime"),
                            "temperature_f": p.get("temperature"),
                            "wind_speed": p.get("windSpeed"),
                            "precip_chance": pop if pop is not None else 0,
                            "short_forecast": p.get("shortForecast"),
                        })
                except Exception as e:  # noqa: BLE001
                    problems.append(f"hourly forecast: {e}")

            # Active alerts for the point
            try:
                ar = client.get(
                    "https://api.weather.gov/alerts/active",
                    params={"point": f"{ctx.latitude:.4f},{ctx.longitude:.4f}"},
                )
                ar.raise_for_status()
                aj = ar.json()
                for feat in aj.get("features", []):
                    ap = feat.get("properties", {})
                    normalized["alerts"].append({
                        "event": ap.get("event"),
                        "severity": ap.get("severity"),
                        "headline": ap.get("headline"),
                        "onset": ap.get("onset"),
                        "ends": ap.get("ends"),
                        "description": (ap.get("description") or "")[:1500],
                        "url": feat.get("id"),
                    })
            except Exception as e:  # noqa: BLE001
                problems.append(f"alerts: {e}")

            # Derived stats across the trip window (rough: all periods returned)
            temps = [p["temperature_f"] for p in normalized["periods"] if p.get("temperature_f") is not None]
            if temps:
                normalized["high_f"] = max(temps)
                normalized["low_f"] = min(temps)
            gusts = [p["wind_max_mph"] for p in normalized["periods"]]
            normalized["max_wind_mph"] = max(gusts) if gusts else 0
            normalized["max_precip_chance"] = max(
                [p["precip_chance"] for p in normalized["periods"]] or [0]
            )
            normalized["snow_mentioned"] = any(
                "snow" in (p.get("short_forecast") or "").lower() for p in normalized["periods"]
            )
            normalized["thunder_mentioned"] = any(
                "thunder" in (p.get("short_forecast") or "").lower() for p in normalized["periods"]
            )
            if problems:
                status = "partial" if normalized["periods"] else "failed"
                normalized["problems"] = problems
            ctx.shared["nws_normalized"] = normalized

            return ConnectorOutput(
                connector_name=NAME,
                status=status,
                source_name=SOURCE,
                source_url=forecast_url or points_url,
                source_timestamp=raw.get("forecast_updated") or utcnow_iso(),
                raw=raw,
                normalized=normalized,
                error_message="; ".join(problems) if problems else None,
            )
    except Exception as e:  # noqa: BLE001
        return failed(NAME, SOURCE, points_url, str(e))
