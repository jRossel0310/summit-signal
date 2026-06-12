"""Background scheduler. One recurring job ("scheduled_checks") re-runs
condition checks for every saved trip on a user-set interval."""
from __future__ import annotations
from apscheduler.schedulers.background import BackgroundScheduler

from . import jobs

scheduler = BackgroundScheduler()
JOB_ID = "scheduled_checks"


def start():
    if not scheduler.running:
        scheduler.start()


def shutdown():
    if scheduler.running:
        scheduler.shutdown(wait=False)


def set_interval_hours(hours: float):
    """hours <= 0 disables the recurring job."""
    existing = scheduler.get_job(JOB_ID)
    if existing:
        existing.remove()
    if hours and hours > 0:
        scheduler.add_job(jobs.run_all_saved_trips, "interval", hours=hours, id=JOB_ID,
                          name=f"Re-check all saved trips every {hours:g} h")


def list_jobs() -> list[dict]:
    return [
        {
            "id": j.id,
            "name": j.name,
            "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
        }
        for j in scheduler.get_jobs()
    ]
