"""
Proves the actual point: a team member who isn't an admin, and has no
hub-wide Tavily/YouTube key to rely on, can still use Web search/YouTube
nodes in their own flows by setting their own personal key on the Account
page - the same personal-overrides-hub-wide pattern already used for the
LLM key and Google app, extended to these two. Also proves a personal key
is truly personal - it doesn't leak to a teammate who didn't set one.
Run with: python3 tests/test_personal_search_keys.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-personalsearch-test-"))
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


def fake_tavily_post(url, json=None, **kwargs):
    return FakeResponse({"results": [{"title": f"result for key {json['api_key']}", "url": "https://x.com", "content": "..."}]})


def fake_youtube_get(url, params=None, **kwargs):
    if "search" in url:
        assert params["key"] == "sams-personal-youtube-key"
        return FakeResponse({"items": [{"id": {"videoId": "v1"}, "snippet": {
            "title": "A video", "channelTitle": "Ch", "description": "d", "publishedAt": "2026-01-01T00:00:00Z",
        }}]})
    return FakeResponse({"items": [{"id": "v1", "statistics": {"viewCount": "10"}}]})


def main():
    client = TestClient(app)
    admin_headers = auth_headers(client, "Alex")  # admin - deliberately configures NO hub-wide search keys
    sam_headers = auth_headers(client, "Sam")      # member - no admin rights

    settings = client.get("/api/settings", headers=admin_headers).json()
    assert settings["web_search_key_configured"] is False
    assert settings["youtube_key_configured"] is False
    print("[ok] hub-wide web search / YouTube keys are NOT configured - the harder case")

    # --- a plain member CAN set their own personal keys (no admin check on Account) ---
    personal = client.put("/api/account/settings", headers=sam_headers, json={
        "web_search_api_key": "sams-personal-tavily-key", "youtube_api_key": "sams-personal-youtube-key",
    }).json()
    assert personal["web_search_key_configured"] is True
    assert personal["youtube_key_configured"] is True
    print("[ok] Sam (a member, not an admin) set personal Tavily + YouTube keys via the Account page")

    # --- a Web search node in Sam's flow uses Sam's personal key ---
    ws_flow = client.post("/api/flows", headers=sam_headers, json={"name": "Sam's search flow"}).json()
    ws_graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "ws", "type": "web_search", "position": {"x": 200, "y": 0}, "data": {"max_results": 3}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "ws"}, {"id": "e2", "source": "ws", "target": "out"}],
    }
    client.put(f"/api/flows/{ws_flow['id']}", headers=sam_headers, json={"graph": ws_graph})
    with patch("httpx.post", side_effect=fake_tavily_post):
        ws_result = client.post(f"/api/flows/{ws_flow['id']}/run", headers=sam_headers, json={"input": "test topic"})
    assert ws_result.status_code == 200, ws_result.text
    assert "sams-personal-tavily-key" in ws_result.json()["output"]
    print("[ok] Sam's Web search node used Sam's own key, with no hub-wide key configured at all")

    # --- a YouTube node in Sam's flow uses Sam's personal key ---
    yt_flow = client.post("/api/flows", headers=sam_headers, json={"name": "Sam's youtube flow"}).json()
    yt_graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "yt", "type": "youtube", "position": {"x": 200, "y": 0}, "data": {"max_results": 3}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "yt"}, {"id": "e2", "source": "yt", "target": "out"}],
    }
    client.put(f"/api/flows/{yt_flow['id']}", headers=sam_headers, json={"graph": yt_graph})
    with patch("httpx.get", side_effect=fake_youtube_get):
        yt_result = client.post(f"/api/flows/{yt_flow['id']}/run", headers=sam_headers, json={"input": "test topic"})
    assert yt_result.status_code == 200, yt_result.text
    assert "A video" in yt_result.json()["output"]
    print("[ok] Sam's YouTube node used Sam's own key too (asserted inside the fake handler)")

    # --- Jordan, who set NEITHER a personal key NOR has a hub-wide one, is still blocked - with a
    # message pointing at both ways to fix it, not just the admin-only one ---
    jordan_headers = auth_headers(client, "Jordan")
    blocked_flow = client.post("/api/flows", headers=jordan_headers, json={"name": "Jordan's flow"}).json()
    client.put(f"/api/flows/{blocked_flow['id']}", headers=jordan_headers, json={"graph": ws_graph})
    blocked_result = client.post(f"/api/flows/{blocked_flow['id']}/run", headers=jordan_headers, json={"input": "x"})
    assert blocked_result.status_code == 400
    assert "Settings page" in str(blocked_result.json()) and "Account page" in str(blocked_result.json())
    print("[ok] a teammate with neither key is still blocked - and told about both ways to fix it")

    print("\nAll personal search-key smoke tests passed.")


if __name__ == "__main__":
    main()
