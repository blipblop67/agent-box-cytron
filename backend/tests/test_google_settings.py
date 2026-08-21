"""
Proves the *new* path works, not just that the old env-var fallback still
does: an admin pastes Google OAuth credentials into the Settings page (no
.env file involved at all), and connecting Gmail immediately works - no
restart needed, since google_oauth.py reads hub_settings on every call.
Run with: python3 tests/test_google_settings.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-google-settings-test-"))
# deliberately NOT setting GOOGLE_CLIENT_ID/SECRET env vars here - the whole
# point of this test is the UI-driven path that doesn't need them
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


def fake_post(url, data=None, **kwargs):
    if url == "https://oauth2.googleapis.com/token":
        assert data["client_id"] == "ui-configured-client-id"
        assert data["client_secret"] == "ui-configured-client-secret"
        return FakeResponse({"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600})
    raise AssertionError(f"unexpected POST {url}")


def fake_get(url, headers=None, **kwargs):
    if url == "https://www.googleapis.com/oauth2/v3/userinfo":
        return FakeResponse({"email": "priya@example.com"})
    raise AssertionError(f"unexpected GET {url}")


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")  # first user -> admin

    # --- before configuring anything: clearly blocked, not a stack trace ---
    settings = client.get("/api/settings", headers=headers).json()
    assert settings["google_client_secret_configured"] is False
    assert settings["google_email_redirect_uri"].endswith("/api/email/auth/callback")
    print(f"[ok] redirect URI is computed automatically: {settings['google_email_redirect_uri']}")

    blocked = client.get("/api/email/auth/start", headers=headers)
    assert blocked.status_code == 500 and "Settings" in blocked.text
    print("[ok] auth/start is blocked with a clear message before credentials are configured")

    # --- a non-admin can't set credentials ---
    other_headers = auth_headers(client, "Sam")
    forbidden = client.put(
        "/api/settings", headers=other_headers,
        json={"google_client_id": "x", "google_client_secret": "y"},
    )
    assert forbidden.status_code == 403
    print("[ok] only a hub admin can configure Google credentials")

    # --- admin configures credentials entirely through the API (no .env) ---
    updated = client.put(
        "/api/settings", headers=headers,
        json={"google_client_id": "ui-configured-client-id", "google_client_secret": "ui-configured-client-secret"},
    ).json()
    assert updated["google_client_id"] == "ui-configured-client-id"
    assert updated["google_client_secret_configured"] is True
    print("[ok] admin configured Google credentials via the Settings API")

    # --- auth/start now works, using exactly the UI-configured client id ---
    start = client.get("/api/email/auth/start", headers=headers).json()
    assert "ui-configured-client-id" in start["authorization_url"]
    print("[ok] auth/start now succeeds and embeds the UI-configured client id")

    # --- the full connect flow works, and the token exchange uses the UI-configured secret ---
    state = start["authorization_url"].split("state=")[1].split("&")[0]
    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        callback = client.get(
            "/api/email/auth/callback", params={"code": "fake-code", "state": state}, follow_redirects=False,
        )
    assert callback.status_code in (302, 307), callback.text
    status = client.get("/api/email/status", headers=headers).json()
    assert status == {"connected": True, "account_email": "priya@example.com", "connected_at": status["connected_at"]}
    print("[ok] connected end-to-end using only UI-configured credentials, no .env involved")

    # --- the secret itself is never echoed back ---
    settings_after = client.get("/api/settings", headers=headers).json()
    assert "google_client_secret" not in settings_after
    assert "ui-configured-client-secret" not in str(settings_after)
    print("[ok] the client secret is never returned by the API, only a 'configured' flag")

    print("\nAll Google-settings-via-UI smoke tests passed.")


if __name__ == "__main__":
    main()
