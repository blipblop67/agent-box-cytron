"""
Direct Calendar action endpoints - list upcoming events, create new ones -
for manual use and testing, plus the OAuth connection lifecycle for Path B
(personal "Connect" flow - see google_oauth.py's docstring). A flow's
Calendar node goes through flow_engine.py directly rather than either of
these; this router is a plain API surface over calendar_client.py, which
does the actual work.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from . import calendar_client, calendar_oauth, calendar_tokens, google_oauth, hub_settings, oauth_errors, oauth_state
from .auth import get_current_user

router = APIRouter(prefix="/calendar", tags=["calendar"])

CALLBACK_PATH = "/api/calendar/auth/callback"


@router.get("/events")
def list_events(max_results: int = 10, impersonate: str | None = None, user: dict = Depends(get_current_user)):
    try:
        return calendar_client.list_events(max_results=max_results, impersonate=impersonate)
    except (ValueError, calendar_client.CalendarError) as exc:
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
    except (ValueError, calendar_client.CalendarError) as exc:
        raise HTTPException(400, str(exc))


# ---- OAuth connection lifecycle (Path B - personal "Connect" flow) --------

@router.get("/status")
def status(user: dict = Depends(get_current_user)):
    return calendar_tokens.get_connection_status(user["id"]) or {"connected": False}


@router.get("/auth/start")
def auth_start(request: Request, user: dict = Depends(get_current_user)):
    client_id, client_secret = hub_settings.get_google_oauth_client()
    if not client_id or not client_secret:
        raise HTTPException(400, "Google OAuth isn't configured for this hub yet - an admin sets this up on Settings")
    state = oauth_state.create(user["id"])
    redirect_uri = google_oauth.redirect_uri_for(request, CALLBACK_PATH)
    return {"authorization_url": calendar_oauth.build_authorization_url(state, redirect_uri, client_id)}


@router.get("/auth/callback")
def auth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return oauth_errors.error_page(
            "Calendar connection failed",
            f"Google reported: <code>{error}</code>. If you didn't cancel the consent screen "
            f"yourself, this almost always means the account needs to be added as a test user.",
        )
    if not code or not state:
        return oauth_errors.error_page("Calendar connection failed", "Google didn't send back an authorization code.")
    user_id = oauth_state.pop(state)
    if user_id is None:
        return oauth_errors.error_page(
            "Calendar connection failed",
            "That connection link expired or was already used - go back to Connections and try again.",
        )
    try:
        client_id, client_secret = hub_settings.get_google_oauth_client()
        redirect_uri = google_oauth.redirect_uri_for(request, CALLBACK_PATH)
        tokens = calendar_oauth.exchange_code_for_tokens(code, redirect_uri, client_id, client_secret)
        account_email = calendar_oauth.fetch_user_email(tokens["access_token"])
        calendar_tokens.save_tokens(user_id, tokens, account_email)
    except Exception as exc:  # noqa: BLE001 - want any failure surfaced to the person, not a raw 500
        return oauth_errors.error_page("Calendar connection failed", f"The connection to Google failed: {exc}")
    return RedirectResponse(url="/connections")


@router.delete("/auth")
def disconnect(user: dict = Depends(get_current_user)):
    calendar_tokens.disconnect(user["id"])
    return {"disconnected": True}
