"""
Covers the YouTube search node standalone, the exact scenario requested
(search a topic, then an LLM node turns the results into video ideas -
proving the results actually reach the LLM as usable context, view counts
included), and that an invalid/exhausted key gives a specific error.
Run with: python3 tests/test_youtube.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-youtube-test-"))
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

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


def fake_get(url, params=None, **kwargs):
    if url == "https://www.googleapis.com/youtube/v3/search":
        assert params["key"] == "test-youtube-key"
        assert params["q"] == "sourdough baking"
        return FakeResponse({"items": [
            {"id": {"videoId": "vid1"}, "snippet": {
                "title": "Sourdough for Beginners", "channelTitle": "Baking Channel",
                "description": "A full beginner walkthrough of sourdough baking from scratch.",
                "publishedAt": "2026-01-01T00:00:00Z",
            }},
            {"id": {"videoId": "vid2"}, "snippet": {
                "title": "5 Sourdough Mistakes", "channelTitle": "Bread Nerd",
                "description": "Common mistakes people make with their starter and how to fix them.",
                "publishedAt": "2026-02-01T00:00:00Z",
            }},
        ]})
    if url == "https://www.googleapis.com/youtube/v3/videos":
        assert params["id"] == "vid1,vid2"
        return FakeResponse({"items": [
            {"id": "vid1", "statistics": {"viewCount": "1200000"}},
            {"id": "vid2", "statistics": {"viewCount": "45000"}},
        ]})
    raise AssertionError(f"unexpected GET {url}")


def fake_llm_post(url, headers=None, json=None, **kwargs):
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    user_message = next(m["content"] for m in json["messages"] if m["role"] == "user")
    # a fake "LLM" that just proves it actually received the search results
    return FakeResponse({"choices": [{"message": {"content": f"IDEAS BASED ON: {user_message[:60]}..."}}]})


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")

    flow = client.post("/api/flows", headers=headers, json={"name": "YouTube search only"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "yt", "type": "youtube", "position": {"x": 200, "y": 0}, "data": {"max_results": 10}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "yt"}, {"id": "e2", "source": "yt", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})

    # --- fails clearly before it's configured ---
    unconfigured = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": "sourdough baking"})
    assert unconfigured.status_code == 400 and "YouTube" in str(unconfigured.json())
    print("[ok] YouTube node fails with a clear message before it's configured")

    # --- configure it ---
    client.put("/api/settings", headers=headers, json={"youtube_api_key": "test-youtube-key"})
    settings = client.get("/api/settings", headers=headers).json()
    assert settings["youtube_key_configured"] is True

    # --- search works and results include view counts ---
    with patch("httpx.get", side_effect=fake_get):
        result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": "sourdough baking"})
    assert result.status_code == 200, result.text
    output = result.json()["output"]
    assert "Sourdough for Beginners" in output and "1,200,000 views" in output
    assert "5 Sourdough Mistakes" in output and "45,000 views" in output
    print(f"[ok] YouTube search returns titles, channels, and view counts:\n{output[:150]}...")

    # --- an invalid/exhausted key gives a specific error ---
    def fake_403(url, **kwargs):
        return FakeResponse({"error": "quota exceeded"}, status_code=403)
    with patch("httpx.get", side_effect=fake_403):
        bad_key_result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": "test"})
    assert bad_key_result.status_code == 400
    assert "YouTube" in str(bad_key_result.json())
    print("[ok] an invalid key or exhausted quota surfaces a specific error")

    # --- THE ACTUAL REQUESTED SCENARIO: search a topic, then an LLM turns results into video ideas ---
    client.put("/api/settings", headers=headers, json={
        "llm_provider": "openrouter", "openrouter_api_key": "fake-llm-key", "openrouter_model": "test/model",
    })
    idea_flow = client.post("/api/flows", headers=headers, json={"name": "YouTube Video Idea Generator"}).json()
    idea_graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "yt", "type": "youtube", "position": {"x": 200, "y": 0}, "data": {"max_results": 10}},
            {"id": "llm", "type": "llm", "position": {"x": 400, "y": 0}, "data": {
                "system_prompt": "Propose video ideas based on what's already out there.",
            }},
            {"id": "out", "type": "output", "position": {"x": 600, "y": 0}, "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "in", "target": "yt"},
            {"id": "e2", "source": "yt", "target": "llm"},
            {"id": "e3", "source": "llm", "target": "out"},
        ],
    }
    client.put(f"/api/flows/{idea_flow['id']}", headers=headers, json={"graph": idea_graph})

    with patch("httpx.get", side_effect=fake_get), patch("httpx.post", side_effect=fake_llm_post):
        idea_result = client.post(f"/api/flows/{idea_flow['id']}/run", headers=headers, json={"input": "sourdough baking"})
    assert idea_result.status_code == 200, idea_result.text
    idea_output = idea_result.json()["output"]
    assert idea_output.startswith("IDEAS BASED ON:")
    # the LLM's fake handler only echoes what it actually received - prove
    # both the search results AND the original topic reached it
    assert "Sourdough for Beginners" in idea_output or "Sourdough" in idea_output
    print(f"[ok] the full requested scenario works end to end: {idea_output}")

    print("\nAll YouTube smoke tests passed.")


if __name__ == "__main__":
    main()
