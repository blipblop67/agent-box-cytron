"""
Proves the "Path B" per-customer Gmail OAuth connection flow works end to
end: an admin configures this hub's own OAuth client, a person clicks
through the authorization-url/callback dance (mocked, since we can't
actually drive Google's consent screen), and their personal connection
becomes usable - all without touching the service account model at all.
Run with: python3 tests/test_gmail_oauth.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-gmailoauth-test-"))
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
    headers = auth_headers(client, "Alex")  # admin

    # --- starts unconfigured - nobody can even start the flow yet ---
    status = client.get("/api/email/status", headers=headers).json()
    assert status == {"connected": False}
    start_unconfigured = client.get("/api/email/auth/start", headers=headers)
    assert start_unconfigured.status_code == 400
    print("[ok] starts unconfigured - can't even begin without an admin setting up OAuth first")

    # --- admin configures this hub's own Google Cloud OAuth client ---
    client.put("/api/settings", headers=headers, json={
        "google_oauth_client_id": "123-abc.apps.googleusercontent.com",
        "google_oauth_client_secret": "shh-its-a-secret",
    })
    settings = client.get("/api/settings", headers=headers).json()
    assert settings["google_oauth_client_secret_configured"] is True
    print("[ok] admin configured this hub's own OAuth client")

    # --- starting the flow now returns a real-shaped Google authorization URL ---
    start_result = client.get("/api/email/auth/start", headers=headers).json()
    assert "accounts.google.com" in start_result["authorization_url"]
    assert "123-abc.apps.googleusercontent.com" in start_result["authorization_url"]
    print(f"[ok] auth/start returns an authorization URL pointed at this hub's own client")

    # --- simulate the callback Google would send after the person approves consent ---
    def fake_post(url, data=None, **kwargs):
        assert data["client_id"] == "123-abc.apps.googleusercontent.com"
        assert data["client_secret"] == "shh-its-a-secret"
        assert data["grant_type"] == "authorization_code"
        return FakeResponse({"access_token": "fresh-access-token", "refresh_token": "a-real-refresh-token", "expires_in": 3600})

    def fake_get(url, headers=None, **kwargs):
        assert headers["Authorization"] == "Bearer fresh-access-token"
        return FakeResponse({"email": "priya@cytron.io"})

    # start a real flow to get a valid, real state token (can't forge one)
    start_result = client.get("/api/email/auth/start", headers=headers).json()
    real_state = start_result["authorization_url"].split("state=")[1].split("&")[0]

    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        callback_result = client.get(
            "/api/email/auth/callback", headers=headers,
            params={"code": "fake-auth-code", "state": real_state},
            follow_redirects=False,
        )
    assert callback_result.status_code in (302, 307)
    assert callback_result.headers["location"] == "/connections"
    print("[ok] the callback exchanged the code for tokens and redirected back to Connections")

    # --- the connection now shows as connected, with the right account email ---
    status_after = client.get("/api/email/status", headers=headers).json()
    assert status_after["connected"] is True
    assert status_after["account_email"] == "priya@cytron.io"
    print(f"[ok] status now shows connected as {status_after['account_email']!r}")

    # --- a reused/expired state token is rejected, not silently accepted ---
    replay_result = client.get(
        "/api/email/auth/callback", headers=headers,
        params={"code": "fake-auth-code", "state": real_state},
    )
    assert replay_result.status_code == 400
    assert b"expired" in replay_result.content or b"already used" in replay_result.content
    print("[ok] replaying the same state token (already used) is rejected, not silently accepted")

    # --- getting a fresh access token later re-refreshes via the stored refresh token,
    # proving the connection is actually usable after the initial connect, not just saved ---
    with db.get_conn() as conn:
        alex_id = conn.execute("SELECT id FROM users WHERE name = ?", ("Alex",)).fetchone()["id"]

    def fake_refresh_post(url, data=None, **kwargs):
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "a-real-refresh-token"
        assert data["client_id"] == "123-abc.apps.googleusercontent.com"
        return FakeResponse({"access_token": "a-second-fresh-token", "expires_in": 3600})

    from app import gmail_tokens
    with patch("httpx.post", side_effect=fake_refresh_post):
        token = gmail_tokens.get_valid_access_token(alex_id)
    assert token == "a-second-fresh-token"
    print(f"[ok] a later call correctly re-refreshes using the stored refresh token: {token!r}")

    # --- disconnecting actually removes the connection ---
    disconnect_result = client.delete("/api/email/auth", headers=headers).json()
    assert disconnect_result == {"disconnected": True}
    status_after_disconnect = client.get("/api/email/status", headers=headers).json()
    assert status_after_disconnect == {"connected": False}
    print("[ok] disconnecting actually removes the connection")

    print("\nAll Gmail OAuth (Path B) smoke tests passed.")


if __name__ == "__main__":
    main()
