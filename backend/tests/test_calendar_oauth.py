"""
Proves the "Path B" per-customer Calendar OAuth connection flow works end
to end - the same proof as test_gmail_oauth.py, for Calendar's own scopes
and routes. See that file for the fuller narrative.
Run with: python3 tests/test_calendar_oauth.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-calendaroauth-test-"))
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


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")

    status = client.get("/api/calendar/status", headers=headers).json()
    assert status == {"connected": False}
    assert client.get("/api/calendar/auth/start", headers=headers).status_code == 400
    print("[ok] starts unconfigured")

    client.put("/api/settings", headers=headers, json={
        "google_oauth_client_id": "123-abc.apps.googleusercontent.com",
        "google_oauth_client_secret": "shh-its-a-secret",
    })

    start_result = client.get("/api/calendar/auth/start", headers=headers).json()
    assert "accounts.google.com" in start_result["authorization_url"]
    assert "calendar.events" in start_result["authorization_url"]
    real_state = start_result["authorization_url"].split("state=")[1].split("&")[0]
    print("[ok] auth/start returns an authorization URL with Calendar's own scope")

    def fake_post(url, data=None, **kwargs):
        return FakeResponse({"access_token": "fresh-token", "refresh_token": "a-refresh-token", "expires_in": 3600})

    def fake_get(url, headers=None, **kwargs):
        return FakeResponse({"email": "priya@cytron.io"})

    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        callback_result = client.get(
            "/api/calendar/auth/callback", headers=headers,
            params={"code": "fake-code", "state": real_state}, follow_redirects=False,
        )
    assert callback_result.status_code in (302, 307)
    print("[ok] callback exchanged the code for tokens and redirected back")

    status_after = client.get("/api/calendar/status", headers=headers).json()
    assert status_after["connected"] is True and status_after["account_email"] == "priya@cytron.io"
    print(f"[ok] status now shows connected as {status_after['account_email']!r}")

    disconnect_result = client.delete("/api/calendar/auth", headers=headers).json()
    assert disconnect_result == {"disconnected": True}
    assert client.get("/api/calendar/status", headers=headers).json() == {"connected": False}
    print("[ok] disconnecting actually removes the connection")

    print("\nAll Calendar OAuth (Path B) smoke tests passed.")


if __name__ == "__main__":
    main()
