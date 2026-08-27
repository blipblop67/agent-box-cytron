"""
Exercises the Calendar integration via the hub-wide service account:
listing upcoming events, creating a new one, and using both from inside a
real flow. Mocks only Google's HTTP APIs.
Run with: python3 tests/test_calendar.py
"""
import json as json_module
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-calendar-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SERVICE_ACCOUNT_KEY = json_module.dumps({
    "type": "service_account",
    "client_email": "sa@sirim-coc-agent.iam.gserviceaccount.com",
    "private_key": _private_key.private_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode(),
    "private_key_id": "fake-key-id",
})


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


_created_events = []


def fake_post(url, data=None, json=None, headers=None, **kwargs):
    if url == "https://oauth2.googleapis.com/token":
        return FakeResponse({"access_token": "impersonated-token", "expires_in": 3600})
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
    assert headers["Authorization"] == "Bearer impersonated-token"
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

    unconfigured = client.get("/api/calendar/events", headers=headers)
    assert unconfigured.status_code == 400 and "service account" in unconfigured.text.lower()
    print("[ok] a clear error when no service account is configured yet")

    client.put("/api/settings", headers=headers, json={"google_service_account_key": SERVICE_ACCOUNT_KEY})
    print("[ok] admin configured the service account key")

    with patch("httpx.get", side_effect=fake_get), patch("httpx.post", side_effect=fake_post):
        events = client.get("/api/calendar/events", headers=headers, params={"impersonate": "priya@cytron.io"}).json()
    assert len(events) == 1 and events[0]["summary"] == "Team standup"
    print(f"[ok] listed {len(events)} upcoming event(s): \"{events[0]['summary']}\"")

    with patch("httpx.post", side_effect=fake_post):
        created = client.post("/api/calendar/events", headers=headers, json={
            "summary": "1:1 with Priya", "start": "2026-09-02T14:00:00", "end": "2026-09-02T14:30:00",
            "timezone_name": "America/New_York", "impersonate": "priya@cytron.io",
        }).json()
    assert created["summary"] == "1:1 with Priya"
    print(f"[ok] created event: \"{created['summary']}\"")

    # --- a flow with a Calendar node (list action) ---
    flow = client.post("/api/flows", headers=headers, json={"name": "Productivity Coach"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "cal", "type": "calendar", "position": {"x": 200, "y": 0}, "data": {
                "action": "list", "max_results": 5, "impersonate": "priya@cytron.io",
            }},
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
                "impersonate": "priya@cytron.io",
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

    print("\nAll Calendar smoke tests passed.")


if __name__ == "__main__":
    main()
