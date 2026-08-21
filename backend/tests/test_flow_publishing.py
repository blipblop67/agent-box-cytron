"""
Proves a published flow is actually callable without any user session -
the whole point of this feature - and that the security properties hold:
only the owner (or an admin) can publish/unpublish, the raw key is only
ever returned once, a wrong key is rejected, and unpublishing immediately
revokes access.
Run with: python3 tests/test_flow_publishing.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-publish-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")
    sam_headers = auth_headers(client, "Sam")

    flow = client.post("/api/flows", headers=headers, json={"name": "Greeter"}).json()
    assert flow["published"] is False
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "out", "type": "output", "position": {"x": 200, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})

    # --- a non-owner can't publish someone else's flow ---
    forbidden = client.post(f"/api/flows/{flow['id']}/publish", headers=sam_headers)
    assert forbidden.status_code == 403
    print("[ok] a non-owner can't publish someone else's flow")

    # --- calling the public endpoint before publishing fails ---
    not_yet = client.post(f"/api/public/flows/{flow['id']}/run", json={"input": "hi"}, headers={"X-API-Key": "whatever"})
    assert not_yet.status_code == 404
    print("[ok] the public endpoint 404s before the flow is published")

    # --- owner publishes it ---
    published = client.post(f"/api/flows/{flow['id']}/publish", headers=headers).json()
    api_key = published["api_key"]
    assert api_key.startswith("ahub_")
    assert published["run_url"] == f"/api/public/flows/{flow['id']}/run"
    print("[ok] published, got a key starting with 'ahub_' and a run_url")

    flow_after = client.get(f"/api/flows/{flow['id']}", headers=headers).json()
    assert flow_after["published"] is True
    print("[ok] the flow now shows published=True (without ever exposing the key again)")

    # --- THE ACTUAL POINT: calling it with the API key and NO session works ---
    no_session_client = TestClient(app)  # a fresh client, no cookies/tokens at all
    result = no_session_client.post(
        f"/api/public/flows/{flow['id']}/run", json={"input": "hello from outside"}, headers={"X-API-Key": api_key},
    )
    assert result.status_code == 200, result.text
    assert result.json()["output"] == "hello from outside"
    print("[ok] called the published flow with zero session/cookies - just the API key - and it worked")

    # --- missing or wrong key is rejected ---
    no_key = no_session_client.post(f"/api/public/flows/{flow['id']}/run", json={"input": "hi"})
    assert no_key.status_code == 401
    wrong_key = no_session_client.post(
        f"/api/public/flows/{flow['id']}/run", json={"input": "hi"}, headers={"X-API-Key": "ahub_wrong-key-entirely"},
    )
    assert wrong_key.status_code == 401
    print("[ok] a missing or wrong API key is rejected")

    # --- the raw key is never returned by any other endpoint ---
    assert "api_key" not in flow_after
    assert api_key not in str(flow_after)
    team_view = client.get("/api/flows", headers=headers).json()
    assert api_key not in str(team_view)
    print("[ok] the raw API key never appears in any other response")

    # --- publishing again rotates the key - the old one stops working ---
    republished = client.post(f"/api/flows/{flow['id']}/publish", headers=headers).json()
    new_key = republished["api_key"]
    assert new_key != api_key
    old_key_now = no_session_client.post(
        f"/api/public/flows/{flow['id']}/run", json={"input": "hi"}, headers={"X-API-Key": api_key},
    )
    assert old_key_now.status_code == 401
    new_key_works = no_session_client.post(
        f"/api/public/flows/{flow['id']}/run", json={"input": "still works"}, headers={"X-API-Key": new_key},
    )
    assert new_key_works.status_code == 200 and new_key_works.json()["output"] == "still works"
    print("[ok] publishing again rotates the key - the old one is immediately dead, the new one works")

    # --- unpublishing revokes access entirely ---
    client.delete(f"/api/flows/{flow['id']}/publish", headers=headers)
    after_unpublish = no_session_client.post(
        f"/api/public/flows/{flow['id']}/run", json={"input": "hi"}, headers={"X-API-Key": new_key},
    )
    assert after_unpublish.status_code == 404
    flow_final = client.get(f"/api/flows/{flow['id']}", headers=headers).json()
    assert flow_final["published"] is False
    print("[ok] unpublishing immediately revokes the key")

    print("\nAll flow-publishing smoke tests passed.")


if __name__ == "__main__":
    main()
