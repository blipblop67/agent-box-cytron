"""
Proves a flow node with auth_mode: "oauth" actually uses the running
user's personal Google connection instead of the service account - the
piece that makes Path B real for actual flows, not just the connection
lifecycle proven in test_gmail_oauth.py / test_drive_oauth.py / etc.
Run with: python3 tests/test_google_oauth_flow_integration.py
"""
import json as json_module
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-oauthflow-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code
        self.text = str(json_data)

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")

    # --- set up an OAuth connection for Alex, the same way test_gmail_oauth.py does ---
    client.put("/api/settings", headers=headers, json={
        "google_oauth_client_id": "123-abc.apps.googleusercontent.com",
        "google_oauth_client_secret": "shh-its-a-secret",
    })
    start_result = client.get("/api/email/auth/start", headers=headers).json()
    real_state = start_result["authorization_url"].split("state=")[1].split("&")[0]

    def fake_token_post(url, data=None, **kwargs):
        return FakeResponse({"access_token": "alex-personal-oauth-token", "refresh_token": "alex-refresh-token", "expires_in": 3600})

    def fake_userinfo_get(url, headers=None, **kwargs):
        return FakeResponse({"email": "alex@cytron.io"})

    with patch("httpx.post", side_effect=fake_token_post), patch("httpx.get", side_effect=fake_userinfo_get):
        client.get("/api/email/auth/callback", headers=headers, params={"code": "fake-code", "state": real_state})
    print("[ok] Alex connected his own Gmail via OAuth")

    # --- build a flow with an Email node explicitly set to auth_mode: oauth ---
    flow = client.post("/api/flows", headers=headers, json={"name": "OAuth Mode Test"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "email", "type": "email", "position": {"x": 200, "y": 0}, "data": {
                "action": "search", "query": "test", "auth_mode": "oauth",
            }},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "email"}, {"id": "e2", "source": "email", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})

    # --- run it: the Gmail API call should use Alex's OAuth token, and the token
    # refresh should happen via the OAuth client, NOT the service account ---
    captured_auth_headers = []

    def fake_refresh_post(url, data=None, **kwargs):
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "alex-refresh-token"
        assert data["client_id"] == "123-abc.apps.googleusercontent.com"
        return FakeResponse({"access_token": "a-freshly-refreshed-token", "expires_in": 3600})

    def fake_gmail_get(url, headers=None, params=None, **kwargs):
        captured_auth_headers.append(headers["Authorization"])
        return FakeResponse({"messages": []})

    with patch("httpx.post", side_effect=fake_refresh_post), patch("httpx.get", side_effect=fake_gmail_get):
        result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": ""})

    assert result.status_code == 200, result.text
    assert captured_auth_headers[0] == "Bearer a-freshly-refreshed-token"
    print(f"[ok] the flow used Alex's personal OAuth token (via refresh), not the service account: {captured_auth_headers[0]!r}")

    # --- the SAME flow, with auth_mode left at its default, uses the service
    # account instead - proving the two modes are genuinely independent, not
    # just "oauth always wins" ---
    default_mode_graph = json_module.loads(json_module.dumps(graph))
    del default_mode_graph["nodes"][1]["data"]["auth_mode"]
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": default_mode_graph})

    service_account_calls = []

    def fake_sa_token_post(url, data=None, **kwargs):
        service_account_calls.append(url)
        return FakeResponse({"access_token": "service-account-token", "expires_in": 3600})

    with patch("httpx.post", side_effect=fake_sa_token_post), patch("httpx.get", side_effect=fake_gmail_get):
        default_result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": ""})
    assert default_result.status_code == 400  # no service account configured in this test - expected
    assert "service account" in default_result.text.lower()
    print("[ok] with auth_mode left at default, the SAME node correctly tries the service account instead")

    # --- a node set to oauth mode, for a user who HASN'T connected, gives a
    # clear, actionable error - not a crash or a confusing failure ---
    sam_headers = auth_headers(client, "Sam")
    unconnected_result = client.post(f"/api/flows/{flow['id']}/run", headers=sam_headers, json={"input": ""})
    # Sam's flow still has auth_mode removed from the graph in this test's last save -
    # rebuild with oauth mode explicitly for this specific check
    oauth_graph_for_sam = json_module.loads(json_module.dumps(graph))
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": oauth_graph_for_sam})
    unconnected_result = client.post(f"/api/flows/{flow['id']}/run", headers=sam_headers, json={"input": ""})
    assert unconnected_result.status_code == 400
    assert "connect" in unconnected_result.text.lower()
    print(f"[ok] a user who hasn't connected their own Google account gets a clear, actionable error")

    print("\nAll Google OAuth flow-integration smoke tests passed.")


if __name__ == "__main__":
    main()
