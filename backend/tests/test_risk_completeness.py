"""Completeness must ignore connectors the user disabled."""
from app.schemas import ConnectorOutput
from app.services import risk_engine

SETTINGS = {"fire_radius_miles": 30, "aqi_moderate_threshold": 101,
            "aqi_major_threshold": 151, "wind_gust_moderate_mph": 30,
            "wind_gust_major_mph": 50, "precip_prob_moderate": 60,
            "cold_low_f": 10, "stale_hours": 24}


def _two_good_and_one_disabled():
    return [
        ConnectorOutput(connector_name="nws_weather", status="success", source_name="NWS"),
        ConnectorOutput(connector_name="usgs_elevation", status="success", source_name="USGS"),
        ConnectorOutput(connector_name="airnow", status="skipped",
                        source_name="AirNow", error_message="Disabled in settings"),
    ]


def test_disabled_connector_excluded_from_completeness():
    enabled = {"airnow": False}  # user turned AirNow off
    _flags, _overall, completeness = risk_engine.evaluate(
        _two_good_and_one_disabled(), SETTINGS, "general", enabled)
    # Only the two enabled, successful connectors count -> 2/2 = 1.0
    assert completeness == 1.0


def test_enabled_failure_lowers_completeness():
    outputs = [
        ConnectorOutput(connector_name="nws_weather", status="success"),
        ConnectorOutput(connector_name="usgs_elevation", status="failed",
                        error_message="boom"),
    ]
    _flags, _overall, completeness = risk_engine.evaluate(
        outputs, SETTINGS, "general", {})
    # success(1) + failed(0) over 2 enabled -> 0.5
    assert completeness == 0.5
