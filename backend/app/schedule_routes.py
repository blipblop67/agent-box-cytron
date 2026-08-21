from fastapi import APIRouter, Depends, HTTPException

from . import db, scheduler
from .auth import get_current_user
from .models import ScheduleCreate, ScheduleOut, ScheduleRunOut, ScheduleUpdate

router = APIRouter(tags=["schedules"])


def _schedule_out(row) -> ScheduleOut:
    return ScheduleOut(**{**dict(row), "enabled": bool(row["enabled"])})


def _require_flow_access(flow_id: str, user: dict):
    flow = db.get_flow(flow_id)
    if flow is None:
        raise HTTPException(404, "Flow not found")
    is_admin = user["role"] == "admin"
    if not db.user_can_access_flow(flow, user["id"], is_admin=is_admin):
        raise HTTPException(403, "This flow is private to another team member")
    return flow


def _require_schedule_access(schedule_id: str, user: dict):
    schedule = db.get_schedule(schedule_id)
    if schedule is None:
        raise HTTPException(404, "Schedule not found")
    _require_flow_access(schedule["flow_id"], user)
    return schedule


def _validate_trigger(body) -> None:
    if body.trigger_type == "interval":
        if not body.interval_minutes or body.interval_minutes < 1:
            raise HTTPException(400, "interval_minutes must be at least 1")
    elif body.trigger_type == "daily":
        if not body.daily_time or len(body.daily_time.split(":")) != 2:
            raise HTTPException(400, "daily_time must be in HH:MM form, e.g. '09:00'")


@router.post("/flows/{flow_id}/schedules", response_model=ScheduleOut)
def create_schedule(flow_id: str, body: ScheduleCreate, user: dict = Depends(get_current_user)):
    _require_flow_access(flow_id, user)
    _validate_trigger(body)
    schedule_id = db.create_schedule(
        flow_id, body.trigger_type, body.interval_minutes, body.daily_time, body.input_text, user["id"],
    )
    scheduler.sync_job(schedule_id)
    return _schedule_out(db.get_schedule(schedule_id))


@router.get("/flows/{flow_id}/schedules", response_model=list[ScheduleOut])
def list_schedules(flow_id: str, user: dict = Depends(get_current_user)):
    _require_flow_access(flow_id, user)
    return [_schedule_out(s) for s in db.list_schedules_for_flow(flow_id)]


@router.patch("/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(schedule_id: str, body: ScheduleUpdate, user: dict = Depends(get_current_user)):
    _require_schedule_access(schedule_id, user)
    db.update_schedule(
        schedule_id, enabled=body.enabled, interval_minutes=body.interval_minutes,
        daily_time=body.daily_time, input_text=body.input_text,
    )
    scheduler.sync_job(schedule_id)
    return _schedule_out(db.get_schedule(schedule_id))


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: str, user: dict = Depends(get_current_user)):
    _require_schedule_access(schedule_id, user)
    scheduler.remove_job(schedule_id)
    db.delete_schedule(schedule_id)
    return {"deleted": schedule_id}


@router.get("/schedules/{schedule_id}/runs", response_model=list[ScheduleRunOut])
def list_schedule_runs(schedule_id: str, user: dict = Depends(get_current_user)):
    _require_schedule_access(schedule_id, user)
    return [ScheduleRunOut(**dict(r)) for r in db.list_schedule_runs(schedule_id)]
