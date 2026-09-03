"""
Thin wrapper around the Google Calendar API v3 - list upcoming events and
create new ones. Raw REST rather than the official Google client library,
same reasoning as service_account_auth.py: three or four endpoints don't
need a whole SDK.

Authenticates entirely through the hub-wide Google service account.
`impersonate` left blank operates on the service account's own calendar
(needs a calendar to actually be shared with its email address first -
its "primary" calendar otherwise has nothing on it). Setting
`impersonate` acts on that Workspace person's own calendar instead
(needs domain-wide delegation authorized for the Calendar scope).
"""
from datetime import datetime, timezone

import httpx

from . import hub_settings, service_account_auth

API_BASE = "https://www.googleapis.com/calendar/v3"

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarError(Exception):
    pass


def _headers(impersonate: str | None = None, access_token: str | None = None) -> dict:
    """access_token, when given, is a resolved per-user OAuth token (Path B),
    used directly, bypassing the service account entirely. Unset is the
    default, unchanged path: the hub-wide service account."""
    if access_token:
        return {"Authorization": f"Bearer {access_token}"}
    key_info = hub_settings.get_service_account_key()
    if key_info is None:
        raise CalendarError("Calendar isn't configured yet - add a Google service account key on the Settings page")
    try:
        token = service_account_auth.get_access_token(key_info, SCOPES, impersonate)
    except service_account_auth.ServiceAccountError as exc:
        raise CalendarError(str(exc)) from exc
    return {"Authorization": f"Bearer {token}"}


def _handle_error(resp: httpx.Response, impersonate: str | None, context: str) -> None:
    if resp.status_code < 400:
        return
    try:
        detail = resp.json().get("error", {}).get("message", resp.text)
    except ValueError:
        detail = resp.text
    if not impersonate:
        raise CalendarError(
            f"Calendar rejected this ({context}: \"{detail}\"). The service account's own primary "
            f"calendar has nothing on it unless a real calendar has been explicitly shared with its "
            f"email address - set this node's 'Impersonate' field to act as a specific Workspace "
            f"person instead if that's what you actually want."
        )
    raise CalendarError(f"Calendar rejected this ({context} as '{impersonate}'): {detail}")


def _now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_events(max_results: int = 10, time_min: str | None = None, *, impersonate: str | None = None,
                 access_token: str | None = None) -> list[dict]:
    """Upcoming events on the primary calendar, soonest first. `time_min`
    defaults to right now, so past events don't show up in what's meant
    to be a "what's coming up" view."""
    params = {
        "maxResults": max_results,
        "singleEvents": True,  # expands recurring events into individual instances
        "orderBy": "startTime",
        "timeMin": time_min or _now_rfc3339(),
    }
    resp = httpx.get(f"{API_BASE}/calendars/primary/events", headers=_headers(impersonate, access_token), params=params, timeout=30)
    _handle_error(resp, impersonate, "listing events")
    return [_parse_event(e) for e in resp.json().get("items", [])]


def create_event(summary: str, start: str, end: str, *,
                  description: str = "", location: str = "", timezone_name: str = "UTC",
                  attendees: list[str] | None = None, impersonate: str | None = None,
                  access_token: str | None = None) -> dict:
    """`start`/`end` are ISO 8601 datetimes (e.g. "2026-09-01T14:00:00") -
    upstream in a flow, an LLM node is the natural place to turn "tomorrow
    at 2pm" into that structured form before it reaches this node, the same
    way an Email node expects an already-resolved address, not free text."""
    body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {"dateTime": start, "timeZone": timezone_name},
        "end": {"dateTime": end, "timeZone": timezone_name},
    }
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees]
    resp = httpx.post(f"{API_BASE}/calendars/primary/events", headers=_headers(impersonate, access_token), json=body, timeout=30)
    _handle_error(resp, impersonate, "creating an event")
    return _parse_event(resp.json())


def _parse_event(data: dict) -> dict:
    start = data.get("start", {})
    end = data.get("end", {})
    return {
        "id": data.get("id"),
        "summary": data.get("summary", "(no title)"),
        "description": data.get("description", ""),
        "location": data.get("location", ""),
        "start": start.get("dateTime") or start.get("date"),  # date-only for all-day events
        "end": end.get("dateTime") or end.get("date"),
        "html_link": data.get("htmlLink"),
    }
