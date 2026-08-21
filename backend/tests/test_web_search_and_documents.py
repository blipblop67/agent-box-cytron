"""
Covers the two smaller new capabilities: a Web search node (mocked Tavily
API) usable standalone or inside a flow, and the one-off document text
extraction endpoint (a Meeting Summarizer doesn't need a whole Knowledge
base just to summarize one transcript).
Run with: python3 tests/test_web_search_and_documents.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-search-test-"))
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


def fake_tavily_post(url, json=None, **kwargs):
    assert url == "https://api.tavily.com/search"
    assert json["api_key"] == "test-tavily-key"
    return FakeResponse({
        "results": [
            {"title": "Best ramen in Shibuya", "url": "https://example.com/ramen", "content": "Ichiran is a popular choice..."},
            {"title": "Shibuya food guide", "url": "https://example.com/guide", "content": "For ramen, try..."},
        ],
    })


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")

    # --- web search fails clearly before it's configured ---
    flow = client.post("/api/flows", headers=headers, json={"name": "Restaurant finder"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "search", "type": "web_search", "position": {"x": 200, "y": 0}, "data": {}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "search"}, {"id": "e2", "source": "search", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})

    unconfigured = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": "ramen in Shibuya"})
    assert unconfigured.status_code == 400 and "Tavily" in str(unconfigured.json())
    print("[ok] web search node fails with a clear message before it's configured")

    # --- configure it, then it works ---
    client.put("/api/settings", headers=headers, json={"web_search_api_key": "test-tavily-key"})
    settings = client.get("/api/settings", headers=headers).json()
    assert settings["web_search_key_configured"] is True

    with patch("httpx.post", side_effect=fake_tavily_post):
        result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": "ramen in Shibuya"})
    assert result.status_code == 200, result.text
    assert "Ichiran" in result.json()["output"]
    assert "Shibuya food guide" in result.json()["output"]
    print("[ok] web search node returns real (mocked) results once configured")

    # --- an invalid Tavily key gives a specific error, not a generic one ---
    def fake_401(url, **kwargs):
        return FakeResponse({"detail": "Unauthorized"}, status_code=401)
    with patch("httpx.post", side_effect=fake_401):
        bad_key_result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": "test"})
    assert bad_key_result.status_code == 400
    assert "Tavily" in str(bad_key_result.json())
    print("[ok] an invalid Tavily key surfaces a specific error")

    # --- extract-text: unsupported file type is rejected ---
    bad_file = {"file": ("archive.zip", b"not a real zip", "application/zip")}
    bad_type = client.post("/api/extract-text", headers=headers, files=bad_file)
    assert bad_type.status_code == 400
    print("[ok] extract-text rejects unsupported file types")

    # --- extract-text: a plain text file round-trips correctly ---
    transcript = "Alice: Let's ship the update Friday.\nBob: Agreed, I'll write the release notes."
    good_file = {"file": ("meeting.txt", transcript, "text/plain")}
    extracted = client.post("/api/extract-text", headers=headers, files=good_file)
    assert extracted.status_code == 200
    assert extracted.json()["content"] == transcript
    assert extracted.json()["filename"] == "meeting.txt"
    print("[ok] extract-text correctly pulls plain text out of an uploaded file")

    # --- an empty file gives a clean error, not a 500 ---
    empty_file = {"file": ("empty.txt", "", "text/plain")}
    empty_result = client.post("/api/extract-text", headers=headers, files=empty_file)
    assert empty_result.status_code == 400
    print("[ok] an empty file is rejected cleanly")

    print("\nAll web search / document extraction smoke tests passed.")


if __name__ == "__main__":
    main()
