"""Condition check routes: status polling, full results, summary regeneration."""
from __future__ import annotations
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..schemas import ConditionCheckOut, ConditionCheckDetail, ConnectorResultOut, RiskFlagOut
from ..services.settings_service import get_settings
from ..services import risk_engine
from ..agent import summarizer

router = APIRouter()


def _detail(check: models.ConditionCheck) -> ConditionCheckDetail:
    results = []
    for r in check.connector_results:
        results.append(ConnectorResultOut(
            id=r.id, connector_name=r.connector_name, status=r.status,
            source_name=r.source_name or "", source_url=r.source_url or "",
            source_timestamp=r.source_timestamp, retrieved_at=r.retrieved_at,
            normalized=json.loads(r.normalized_json) if r.normalized_json else None,
            error_message=r.error_message,
        ))
    flags = [RiskFlagOut(id=f.id, severity=f.severity, category=f.category, title=f.title,
                         description=f.description, source_connector=f.source_connector,
                         source_url=f.source_url, confidence=f.confidence)
             for f in check.risk_flags]
    return ConditionCheckDetail(
        id=check.id, trip_id=check.trip_id, started_at=check.started_at,
        completed_at=check.completed_at, status=check.status,
        overall_concern_status=check.overall_concern_status,
        data_completeness_score=check.data_completeness_score,
        summary_text=check.summary_text,
        connector_results=results, risk_flags=flags,
        ai_summary=check.summary_text, ai_generator=None,
    )


@router.get("/condition-checks/{check_id}", response_model=ConditionCheckDetail)
def get_check(check_id: int, db: Session = Depends(get_db)):
    check = db.get(models.ConditionCheck, check_id)
    if not check:
        raise HTTPException(404, "Condition check not found")
    detail = _detail(check)
    latest = (db.query(models.AiSummary).filter_by(condition_check_id=check_id)
              .order_by(models.AiSummary.created_at.desc()).first())
    if latest:
        detail.ai_summary = latest.summary_markdown
        detail.ai_generator = latest.generator
    return detail


@router.get("/condition-checks/{check_id}/status", response_model=ConditionCheckOut)
def get_check_status(check_id: int, db: Session = Depends(get_db)):
    check = db.get(models.ConditionCheck, check_id)
    if not check:
        raise HTTPException(404, "Condition check not found")
    return ConditionCheckOut(
        id=check.id, trip_id=check.trip_id, started_at=check.started_at,
        completed_at=check.completed_at, status=check.status,
        overall_concern_status=check.overall_concern_status,
        data_completeness_score=check.data_completeness_score,
        summary_text=None,
    )


@router.get("/condition-checks/{check_id}/results", response_model=ConditionCheckDetail)
def get_check_results(check_id: int, db: Session = Depends(get_db)):
    return get_check(check_id, db)


@router.post("/condition-checks/{check_id}/generate-summary")
def regenerate_summary(check_id: int, db: Session = Depends(get_db)):
    check = db.get(models.ConditionCheck, check_id)
    if not check:
        raise HTTPException(404, "Condition check not found")
    if check.status != "complete":
        raise HTTPException(409, "Condition check has not completed yet")
    trip = db.get(models.Trip, check.trip_id)
    settings = get_settings(db)
    outputs = []
    for r in check.connector_results:
        outputs.append({
            "connector_name": r.connector_name, "status": r.status,
            "source_name": r.source_name, "source_url": r.source_url,
            "source_timestamp": r.source_timestamp,
            "normalized": json.loads(r.normalized_json) if r.normalized_json else None,
            "error_message": r.error_message,
        })
    flags = [{"severity": f.severity, "category": f.category, "title": f.title,
              "description": f.description, "source_connector": f.source_connector,
              "source_url": f.source_url, "confidence": f.confidence}
             for f in check.risk_flags]
    # rebuild checklist from stored connector envelopes
    from ..schemas import ConnectorOutput
    envs = [ConnectorOutput(**{**o, "raw": None}) for o in outputs]
    checklist = risk_engine.build_manual_checklist(envs, trip.trip_type)
    trip_dict = {"name": trip.name, "location_name": trip.location_name,
                 "latitude": trip.latitude, "longitude": trip.longitude,
                 "start_date": trip.start_date, "end_date": trip.end_date,
                 "trip_type": trip.trip_type}
    md, generator = summarizer.summarize(trip_dict, flags, outputs, checklist, settings)
    db.add(models.AiSummary(condition_check_id=check_id, generator=generator,
                            summary_markdown=md))
    check.summary_text = md
    db.commit()
    return {"generator": generator, "summary_markdown": md}
