"""
Proves per-user overrides actually take priority: a personal Google app
takes over the OAuth flow for that user (and only that user - a teammate
without one still uses the hub default), and a personal OpenRouter key gets
used by a flow that user runs instead of the hub-wide key.
Run with: python3 tests/test_personal_settings.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-personal-test-"))
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


def fake_llm_post(url, headers=None, json=None, **kwargs):
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    return FakeResponse({
        "choices": [{"message": {"content": f"used-key:{headers['Authorization']} used-model:{json['model']}"}}],
    })


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")  # first user -> admin, sets the hub-wide defaults
    sam_headers = auth_headers(client, "Sam")  # a regular member with no personal Google app

    client.put("/api/settings", headers=headers, json={
        "llm_provider": "openrouter", "openrouter_api_key": "hub-wide-key", "openrouter_model": "hub/model",
    })
    client.put("/api/settings", headers=headers, json={
        "google_client_id": "hub-wide-client-id", "google_client_secret": "hub-wide-secret",
    })

    # --- before setting anything personal, Alex's Account page shows the hub defaults aren't personal ones ---
    personal = client.get("/api/account/settings", headers=headers).json()
    assert personal["google_client_id"] == ""
    assert personal["openrouter_key_configured"] is False
    print("[ok] personal settings start empty even though hub-wide ones are set")

    # --- Alex sets up their OWN Google app ---
    updated = client.put("/api/account/settings", headers=headers, json={
        "google_client_id": "alex-personal-client-id", "google_client_secret": "alex-personal-secret",
    }).json()
    assert updated["google_client_id"] == "alex-personal-client-id"
    print("[ok] Alex configured a personal Google app")

    # --- Alex's Gmail connect flow now uses THEIR OWN client id, not the hub's ---
    start = client.get("/api/email/auth/start", headers=headers).json()
    assert "alex-personal-client-id" in start["authorization_url"]
    assert "hub-wide-client-id" not in start["authorization_url"]
    print("[ok] Alex's own Google app is used for Alex's Gmail connect flow")

    # --- Sam, who has NOT set a personal Google app, still uses the hub-wide one ---
    sam_start = client.get("/api/email/auth/start", headers=sam_headers).json()
    assert "hub-wide-client-id" in sam_start["authorization_url"]
    assert "alex-personal-client-id" not in sam_start["authorization_url"]
    print("[ok] Sam (no personal app) falls back to the hub-wide Google app")

    # --- Alex sets a personal OpenRouter key + model ---
    client.put("/api/account/settings", headers=headers, json={
        "openrouter_api_key": "alex-personal-key", "openrouter_model": "alex/preferred-model",
    })

    # --- a flow Alex runs uses Alex's personal key/model ---
    flow = client.post("/api/flows", headers=headers, json={"name": "Personal key test"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "llm", "type": "llm", "position": {"x": 200, "y": 0}, "data": {}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "llm"}, {"id": "e2", "source": "llm", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})

    with patch("httpx.post", side_effect=fake_llm_post):
        result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": "hi"})
    assert result.status_code == 200, result.text
    output = result.json()["output"]
    assert "alex-personal-key" in output
    assert "alex/preferred-model" in output
    assert "hub-wide-key" not in output
    print(f"[ok] Alex's flow run used the personal key/model: {output}")

    # --- Sam runs the SAME flow (it's shared) and still gets the hub-wide key ---
    with patch("httpx.post", side_effect=fake_llm_post):
        sam_result = client.post(f"/api/flows/{flow['id']}/run", headers=sam_headers, json={"input": "hi"})
    sam_output = sam_result.json()["output"]
    assert "hub-wide-key" in sam_output
    assert "hub/model" in sam_output
    assert "alex-personal-key" not in sam_output
    print(f"[ok] Sam's run of the same shared flow used the hub-wide key/model: {sam_output}")

    # --- the personal secret itself is never returned by the API ---
    check = client.get("/api/account/settings", headers=headers).json()
    assert "alex-personal-key" not in str(check)
    assert "alex-personal-secret" not in str(check)
    assert check["openrouter_key_configured"] is True
    print("[ok] personal secrets never appear in API responses, only a 'configured' flag")

    print("\nAll personal-settings smoke tests passed.")


if __name__ == "__main__":
    main()
