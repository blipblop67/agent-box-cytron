"""
Thin wrapper around the Google Calendar API v3 - list upcoming events and
create new ones. Raw REST rather than the official Google client library,
same reasoning as gmail_client.py/drive_client.py: three or four endpoints
don't need a whole SDK.

Every function takes an optional `impersonate` email - see gmail_client.py's
docstring for why this is a separate auth path from personal OAuth, not a
flag on the same one.
"""
from datetime import datetime, timezone

import httpx

from . import calendar_tokens, hub_settings, service_account_auth

API_BASE = "https://www.googleapis.com/calendar/v3"

IMPERSONATION_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _headers(user_id: str, impersonate: str | None = None) -> dict:
    if impersonate:
        key_info = hub_settings.get_service_account_key()
        if key_info is None:
            raise ValueError(
                "This node is set to act as a specific person, but no Google service account is "
                "configured on the Settings page yet."
            )
        token = service_account_auth.get_access_token_for(key_info, impersonate, IMPERSONATION_SCOPES)
    else:
        token = calendar_tokens.get_valid_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def _now_rfc3339() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_events(user_id: str, max_results: int = 10, time_min: str | None = None,
                 *, impersonate: str | None = None) -> list[dict]:
    """Upcoming events on the person's primary calendar, soonest first.
    `time_min` defaults to right now, so past events don't show up in
    what's meant to be a "what's coming up" view."""
    params = {
        "maxResults": max_results,
        "singleEvents": True,  # expands recurring events into individual instances
        "orderBy": "startTime",
        "timeMin": time_min or _now_rfc3339(),
    }
    resp = httpx.get(f"{API_BASE}/calendars/primary/events", headers=_headers(user_id, impersonate), params=params, timeout=30)
    resp.raise_for_status()
    return [_parse_event(e) for e in resp.json().get("items", [])]


def create_event(user_id: str, summary: str, start: str, end: str, *,
                  description: str = "", location: str = "", timezone_name: str = "UTC",
                  attendees: list[str] | None = None, impersonate: str | None = None) -> dict:
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
    resp = httpx.post(f"{API_BASE}/calendars/primary/events", headers=_headers(user_id, impersonate), json=body, timeout=30)
    resp.raise_for_status()
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
