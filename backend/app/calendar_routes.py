"""
Direct Calendar action endpoints - list upcoming events, create new ones -
for manual use and testing. A flow's Calendar node goes through
flow_engine.py directly rather than these; this router is a plain API
surface over calendar_client.py, which does the actual work.

There's no per-user "connect" step anymore - Calendar authenticates
entirely through the hub-wide Google service account (see
service_account_auth.py and hub_settings.py). `impersonate` (a Workspace
email) is optional - left blank, everything happens on the service
account's own calendar.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import calendar_client, service_account_auth
from .auth import get_current_user

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("/events")
def list_events(max_results: int = 10, impersonate: str | None = None, user: dict = Depends(get_current_user)):
    try:
        return calendar_client.list_events(max_results=max_results, impersonate=impersonate)
    except (ValueError, service_account_auth.ServiceAccountError) as exc:
        raise HTTPException(400, str(exc))


class CreateEventRequest(BaseModel):
    summary: str
    start: str
    end: str
    description: str = ""
    location: str = ""
    timezone_name: str = "UTC"
    attendees: list[str] | None = None
    impersonate: str | None = None


@router.post("/events")
def create_event(body: CreateEventRequest, user: dict = Depends(get_current_user)):
    try:
        return calendar_client.create_event(
            summary=body.summary, start=body.start, end=body.end,
            description=body.description, location=body.location,
            timezone_name=body.timezone_name, attendees=body.attendees, impersonate=body.impersonate,
        )
    except (ValueError, service_account_auth.ServiceAccountError) as exc:
        raise HTTPException(400, str(exc))
