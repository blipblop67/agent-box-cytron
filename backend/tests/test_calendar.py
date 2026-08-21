"""
Exercises the Calendar integration end to end: OAuth connect (mocked
against Google), listing upcoming events, creating a new one, and using
both from inside a real flow. Mocks only Google's HTTP APIs.
Run with: python3 tests/test_calendar.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-calendar-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


class FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


_created_events = []


def fake_post(url, data=None, json=None, headers=None, **kwargs):
    if url == "https://oauth2.googleapis.com/token":
        return FakeResponse({"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600})
    if url == "https://www.googleapis.com/calendar/v3/calendars/primary/events":
        event = {
            "id": f"evt-{len(_created_events) + 1}",
            "summary": json["summary"],
            "description": json.get("description", ""),
            "location": json.get("location", ""),
            "start": json["start"],
            "end": json["end"],
            "htmlLink": "https://calendar.google.com/event?eid=fake",
        }
        _created_events.append(event)
        return FakeResponse(event)
    raise AssertionError(f"unexpected POST {url}")


def fake_get(url, headers=None, params=None, **kwargs):
    if url == "https://www.googleapis.com/oauth2/v3/userinfo":
        return FakeResponse({"email": "priya@example.com"})
    if url == "https://www.googleapis.com/calendar/v3/calendars/primary/events":
        return FakeResponse({"items": [
            {
                "id": "evt-existing",
                "summary": "Team standup",
                "location": "Zoom",
                "start": {"dateTime": "2026-09-01T09:00:00Z"},
                "end": {"dateTime": "2026-09-01T09:15:00Z"},
            },
        ]})
    raise AssertionError(f"unexpected GET {url}")


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Priya")

    # --- not connected yet ---
    status = client.get("/api/calendar/status", headers=headers).json()
    assert status == {"connected": False}
    print("[ok] starts disconnected")

    client.put("/api/settings", headers=headers, json={
        "google_client_id": "test-client-id", "google_client_secret": "test-client-secret",
    })

    # --- full OAuth connect flow (mocked) ---
    start = client.get("/api/calendar/auth/start", headers=headers).json()
    assert "authorization_url" in start
    state = start["authorization_url"].split("state=")[1].split("&")[0]
    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        callback = client.get("/api/calendar/auth/callback", params={"code": "fake-code", "state": state}, follow_redirects=False)
    assert callback.status_code in (302, 307)
    print("[ok] OAuth connect flow completed")

    status_after = client.get("/api/calendar/status", headers=headers).json()
    assert status_after["connected"] is True and status_after["account_email"] == "priya@example.com"
    print("[ok] now connected as priya@example.com")

    # --- list upcoming events ---
    with patch("httpx.get", side_effect=fake_get), patch("httpx.post", side_effect=fake_post):
        events = client.get("/api/calendar/events", headers=headers).json()
    assert len(events) == 1 and events[0]["summary"] == "Team standup"
    print(f"[ok] listed {len(events)} upcoming event(s): \"{events[0]['summary']}\"")

    # --- create a new event ---
    with patch("httpx.post", side_effect=fake_post):
        created = client.post("/api/calendar/events", headers=headers, json={
            "summary": "1:1 with Priya", "start": "2026-09-02T14:00:00", "end": "2026-09-02T14:30:00",
            "timezone_name": "America/New_York",
        }).json()
    assert created["summary"] == "1:1 with Priya"
    print(f"[ok] created event: \"{created['summary']}\"")

    # --- a flow with a Calendar node (list action) ---
    flow = client.post("/api/flows", headers=headers, json={"name": "Productivity Coach"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "cal", "type": "calendar", "position": {"x": 200, "y": 0}, "data": {"action": "list", "max_results": 5}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "cal"}, {"id": "e2", "source": "cal", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})
    with patch("httpx.get", side_effect=fake_get), patch("httpx.post", side_effect=fake_post):
        result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": ""})
    assert result.status_code == 200, result.text
    assert "Team standup" in result.json()["output"]
    print(f"[ok] flow with a Calendar (list) node ran: \"{result.json()['output']}\"")

    # --- a flow with a Calendar node (create action), description flows from upstream input ---
    create_flow = client.post("/api/flows", headers=headers, json={"name": "Schedule a follow-up"}).json()
    create_graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "cal", "type": "calendar", "position": {"x": 200, "y": 0}, "data": {
                "action": "create", "summary": "Follow-up call", "start": "2026-09-03T10:00:00", "end": "2026-09-03T10:30:00",
            }},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "cal"}, {"id": "e2", "source": "cal", "target": "out"}],
    }
    client.put(f"/api/flows/{create_flow['id']}", headers=headers, json={"graph": create_graph})
    with patch("httpx.post", side_effect=fake_post):
        create_result = client.post(f"/api/flows/{create_flow['id']}/run", headers=headers, json={"input": "Discuss Q4 roadmap"})
    assert create_result.status_code == 200, create_result.text
    assert "Follow-up call" in create_result.json()["output"]
    assert _created_events[-1]["description"] == "Discuss Q4 roadmap"
    print(f"[ok] flow with a Calendar (create) node ran, description came from upstream input: \"{create_result.json()['output']}\"")

    # --- missing required fields gives a clear error, not a raw exception ---
    incomplete_flow = client.post("/api/flows", headers=headers, json={"name": "Broken calendar node"}).json()
    incomplete_graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "cal", "type": "calendar", "position": {"x": 200, "y": 0}, "data": {"action": "create"}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "cal"}, {"id": "e2", "source": "cal", "target": "out"}],
    }
    client.put(f"/api/flows/{incomplete_flow['id']}", headers=headers, json={"graph": incomplete_graph})
    broken_result = client.post(f"/api/flows/{incomplete_flow['id']}/run", headers=headers, json={"input": "x"})
    assert broken_result.status_code == 400
    assert "title, start time, and end time" in str(broken_result.json())
    print("[ok] a Calendar create node missing required fields gives a clear error")

    # --- disconnect ---
    client.delete("/api/calendar/auth", headers=headers)
    assert client.get("/api/calendar/status", headers=headers).json() == {"connected": False}
    print("[ok] disconnect works")

    print("\nAll Calendar smoke tests passed.")


if __name__ == "__main__":
    main()
