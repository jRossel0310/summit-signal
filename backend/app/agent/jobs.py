"""Local agent job: run a full condition check for a trip.

Runs connectors in dependency order (weather and elevation first because other
connectors read their shared context), persists every connector result, runs
the risk engine, and writes the summary. Each connector failure is contained —
a failed source becomes a data-gap flag, never a crash.
"""
from __future__ import annotations
import datetime as dt
import json
import threading
import traceback

from sqlalchemy.orm import Session

from .. import models
from ..database import SessionLocal
from ..schemas import ConnectorOutput
from ..connectors import (
    nws_weather, usgs_elevation, elevation_adjusted, nasa_firms,
    nifc_wfigs, airnow, nps_alerts, avalanche, weather_discussion,
)
from ..connectors.base import ConnectorContext
from ..services import risk_engine
from ..services.settings_service import get_settings, get_api_key
from . import summarizer

# Order matters: nws_weather and usgs_elevation populate shared context.
CONNECTOR_PIPELINE = [
    ("nws_weather", nws_weather),
    ("usgs_elevation", usgs_elevation),
    ("elevation_adjusted", elevation_adjusted),
    ("nasa_firms", nasa_firms),
    ("nifc_wfigs", nifc_wfigs),
    ("airnow", airnow),
    ("nps_alerts", nps_alerts),
    ("avalanche", avalanche),
    ("weather_discussion", weather_discussion),
]


def start_condition_check(trip_id: int) -> int:
    """Create the check row and kick off a worker thread. Returns check id."""
    db = SessionLocal()
    try:
        trip = db.get(models.Trip, trip_id)
        if trip is None:
            raise ValueError(f"Trip {trip_id} not found")
        check = models.ConditionCheck(trip_id=trip_id, status="running")
        db.add(check)
        db.commit()
        db.refresh(check)
        check_id = check.id
    finally:
        db.close()
    threading.Thread(target=_run_check, args=(check_id,), daemon=True).start()
    return check_id


def _run_check(check_id: int):
    db = SessionLocal()
    try:
        check = db.get(models.ConditionCheck, check_id)
        trip = db.get(models.Trip, check.trip_id)
        settings = get_settings(db)
        enabled = settings.get("connectors_enabled", {})
        api_keys = {name: get_api_key(db, name) for name in ("firms", "airnow", "nps")}

        bbox = None
        gpx_meta = {}
        if trip.gpx_route_id:
            route = db.get(models.GpxRoute, trip.gpx_route_id)
            if route:
                bbox = json.loads(route.bbox_json) if route.bbox_json else None
                gpx_meta = {"min_elevation_ft": route.min_elevation_ft,
                            "max_elevation_ft": route.max_elevation_ft,
                            "length_miles": route.length_miles}

        ctx = ConnectorContext(
            latitude=trip.latitude, longitude=trip.longitude,
            start_date=trip.start_date, end_date=trip.end_date,
            trip_type=trip.trip_type, bbox=bbox,
            elevation_bands=json.loads(trip.elevation_bands) if trip.elevation_bands else None,
            settings=settings, api_keys=api_keys,
            shared={"gpx_meta": gpx_meta},
        )

        outputs: list[ConnectorOutput] = []
        for name, module in CONNECTOR_PIPELINE:
            if not enabled.get(name, True):
                out = ConnectorOutput(connector_name=name, status="skipped",
                                      error_message="Disabled in settings")
            else:
                try:
                    out = module.run(ctx)
                except Exception as e:  # noqa: BLE001 — connectors shouldn't raise, but belt & braces
                    out = ConnectorOutput(connector_name=name, status="failed",
                                          error_message=f"{e}\n{traceback.format_exc()[:500]}")
            outputs.append(out)
            db.add(models.ConnectorResult(
                condition_check_id=check_id,
                connector_name=out.connector_name,
                status=out.status,
                source_name=out.source_name,
                source_url=out.source_url,
                source_timestamp=out.source_timestamp,
                raw_json=json.dumps(out.raw, default=str) if out.raw is not None else None,
                normalized_json=json.dumps(out.normalized, default=str)
                if out.normalized is not None else None,
                error_message=out.error_message,
            ))
            db.commit()

        flags, overall, completeness = risk_engine.evaluate(
            outputs, settings, trip.trip_type, enabled)
        for f in flags:
            db.add(models.RiskFlag(condition_check_id=check_id, **f))

        checklist = risk_engine.build_manual_checklist(outputs, trip.trip_type)
        trip_dict = {
            "name": trip.name, "location_name": trip.location_name,
            "latitude": trip.latitude, "longitude": trip.longitude,
            "start_date": trip.start_date, "end_date": trip.end_date,
            "trip_type": trip.trip_type,
        }
        output_dicts = [o.model_dump() for o in outputs]
        summary_md, generator = summarizer.summarize(
            trip_dict, flags, output_dicts, checklist, settings)

        db.add(models.AiSummary(condition_check_id=check_id, generator=generator,
                                summary_markdown=summary_md))
        check.status = "complete"
        check.completed_at = dt.datetime.now(dt.timezone.utc)
        check.overall_concern_status = overall
        check.data_completeness_score = completeness
        check.summary_text = summary_md
        trip.last_checked_at = check.completed_at
        trip.latest_concern_status = overall
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        check = db.get(models.ConditionCheck, check_id)
        if check:
            check.status = "failed"
            check.completed_at = dt.datetime.now(dt.timezone.utc)
            check.overall_concern_status = "Source check failed"
            check.summary_text = f"Condition check failed: {e}"
            db.commit()
    finally:
        db.close()


def run_all_saved_trips() -> list[int]:
    db = SessionLocal()
    try:
        trip_ids = [t.id for t in db.query(models.Trip).all()]
    finally:
        db.close()
    return [start_condition_check(tid) for tid in trip_ids]
