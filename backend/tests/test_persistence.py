"""Deleting a trip must remove every descendant row (no orphans)."""
from app import models


def _make_full_trip(session):
    trip = models.Trip(name="T", latitude=46.0, longitude=-121.0,
                       start_date="2026-07-01", end_date="2026-07-03")
    session.add(trip)
    session.flush()
    check = models.ConditionCheck(trip_id=trip.id, status="complete")
    session.add(check)
    session.flush()
    session.add(models.ConnectorResult(condition_check_id=check.id,
                                       connector_name="nws_weather", status="success"))
    session.add(models.RiskFlag(condition_check_id=check.id, title="x"))
    session.add(models.AiSummary(condition_check_id=check.id, summary_markdown="s"))
    session.add(models.SavedReport(trip_id=trip.id, condition_check_id=check.id, html="<p>r</p>"))
    session.commit()
    return trip.id


def test_delete_trip_cascades_all_children(session):
    trip_id = _make_full_trip(session)
    trip = session.get(models.Trip, trip_id)
    session.delete(trip)
    session.commit()

    assert session.query(models.ConditionCheck).count() == 0
    assert session.query(models.ConnectorResult).count() == 0
    assert session.query(models.RiskFlag).count() == 0
    assert session.query(models.AiSummary).count() == 0
    assert session.query(models.SavedReport).count() == 0
