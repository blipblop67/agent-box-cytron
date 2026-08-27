"""
Proves per-user overrides actually take priority: a personal OpenRouter
key gets used by a flow that user runs instead of the hub-wide key, and a
teammate without one still uses the hub default.

Google has no personal-override concept anymore - it's a single hub-wide
service account (see test_service_account_impersonation.py), which isn't
the kind of credential that makes sense to have a personal alternative to.
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
    sam_headers = auth_headers(client, "Sam")  # a regular member with no personal key

    client.put("/api/settings", headers=headers, json={
        "llm_provider": "openrouter", "openrouter_api_key": "hub-wide-key", "openrouter_model": "hub/model",
    })

    # --- before setting anything personal, Alex's Account page shows nothing personal is set ---
    personal = client.get("/api/account/settings", headers=headers).json()
    assert personal["openrouter_key_configured"] is False
    print("[ok] personal settings start empty even though hub-wide ones are set")

    # --- Alex sets a personal OpenRouter key + model ---
    client.put("/api/account/settings", headers=headers, json={
        "openrouter_api_key": "alex-personal-key", "openrouter_model": "alex/preferred-model",
    })
    print("[ok] Alex configured a personal OpenRouter key")

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
    assert check["openrouter_key_configured"] is True
    print("[ok] personal secrets never appear in API responses, only a 'configured' flag")

    print("\nAll personal-settings smoke tests passed.")


if __name__ == "__main__":
    main()
