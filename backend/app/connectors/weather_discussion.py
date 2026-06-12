"""Official Weather Discussion Connector.

Pulls the latest NWS Area Forecast Discussion (AFD) for the forecast office
that covers the selected point (office is shared by the nws_weather connector),
then extracts sentences mentioning mountaineering-relevant language: wind,
storms, precipitation, snow, freezing level, heat, severe weather, uncertainty.
"""
from __future__ import annotations
import re
from .base import ConnectorContext, http_client, failed, skipped, utcnow_iso
from ..schemas import ConnectorOutput

NAME = "weather_discussion"
SOURCE = "NWS Area Forecast Discussion"
KEYWORDS = {
    "wind": ["wind", "gust", "breezy"],
    "storms": ["thunderstorm", "storm system", "convect", "lightning"],
    "precipitation": ["rain", "precip", "shower", "qpf"],
    "snow": ["snow", "winter weather", "blizzard", "accumulation"],
    "freezing_level": ["freezing level", "snow level"],
    "heat": ["heat", "hot temperatures", "record high"],
    "severe": ["severe", "warning", "watch", "advisory", "hazard"],
    "uncertainty": ["uncertain", "confidence", "model spread", "disagree"],
}


def run(ctx: ConnectorContext) -> ConnectorOutput:
    office = ctx.shared.get("nws_office")
    if not office:
        return skipped(NAME, SOURCE, "No NWS forecast office identified (weather check failed)")
    list_url = f"https://api.weather.gov/products/types/AFD/locations/{office}"
    try:
        with http_client() as client:
            r = client.get(list_url)
            r.raise_for_status()
            items = r.json().get("@graph", [])
            if not items:
                return skipped(NAME, SOURCE, f"No AFD products found for office {office}")
            latest = items[0]
            pr = client.get(latest["@id"])
            pr.raise_for_status()
            product = pr.json()
            text = product.get("productText", "")
            issuance = product.get("issuanceTime")

            sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text))
            highlights: dict[str, list[str]] = {}
            for topic, words in KEYWORDS.items():
                hits = [s.strip() for s in sentences
                        if any(w in s.lower() for w in words) and 30 < len(s) < 400]
                if hits:
                    highlights[topic] = hits[:4]

            normalized = {
                "office": office,
                "issued": issuance,
                "highlights": highlights,
                "full_text_chars": len(text),
                "excerpt": text[:2500],
            }
            return ConnectorOutput(
                connector_name=NAME, status="success", source_name=f"{SOURCE} ({office})",
                source_url=f"https://forecast.weather.gov/product.php?site={office}&issuedby={office}&product=AFD",
                source_timestamp=issuance or utcnow_iso(),
                raw={"product_id": latest.get("id")}, normalized=normalized,
            )
    except Exception as e:  # noqa: BLE001
        return failed(NAME, SOURCE, list_url, str(e))
