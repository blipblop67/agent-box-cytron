"""
Regression test for a real bug found while building the Calendar
integration: when a tool node (Knowledge base, Web search, Calendar, ...)
ran before an LLM node, the LLM only ever saw the tool's output as its
"user message" - the person's actual question was silently discarded by
the time it reached the model. A Knowledge base node's search results
never mention what was asked; a Calendar listing never mentions what the
person actually said. This proves the LLM node now receives both.
Run with: python3 tests/test_llm_node_context.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-llmctx-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()

_seen_messages = []


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": "ok"}}]}


def fake_llm_post(url, headers=None, json=None, **kwargs):
    _seen_messages.append(json["messages"])
    return FakeResponse()


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")
    client.put("/api/settings", headers=headers, json={
        "llm_provider": "openrouter", "openrouter_api_key": "test-key", "openrouter_model": "test/model",
    })

    # --- a tool (Calculator, standing in for any tool node) runs before the LLM ---
    flow = client.post("/api/flows", headers=headers, json={"name": "Tool then LLM"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "calc", "type": "calculator", "position": {"x": 200, "y": 0}, "data": {"expression": "40 + 2"}},
            {"id": "llm", "type": "llm", "position": {"x": 400, "y": 0}, "data": {"system_prompt": "You are helpful."}},
            {"id": "out", "type": "output", "position": {"x": 600, "y": 0}, "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "in", "target": "calc"},
            {"id": "e2", "source": "calc", "target": "llm"},
            {"id": "e3", "source": "llm", "target": "out"},
        ],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})

    with patch("httpx.post", side_effect=fake_llm_post):
        result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": "what does this number mean for my budget?"})
    assert result.status_code == 200, result.text

    user_message = next(m["content"] for m in _seen_messages[-1] if m["role"] == "user")
    assert "42" in user_message, f"tool output missing from LLM context: {user_message!r}"
    assert "what does this number mean for my budget?" in user_message, (
        f"THE BUG: the original message never reached the LLM - it only saw the tool output: {user_message!r}"
    )
    print(f"[ok] the LLM received both the tool's output and the original message: {user_message!r}")

    # --- a plain Input -> LLM chain (no tool) is unaffected - no 'Context:' framing added ---
    simple_flow = client.post("/api/flows", headers=headers, json={"name": "Just LLM"}).json()
    simple_graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "llm", "type": "llm", "position": {"x": 200, "y": 0}, "data": {}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "llm"}, {"id": "e2", "source": "llm", "target": "out"}],
    }
    client.put(f"/api/flows/{simple_flow['id']}", headers=headers, json={"graph": simple_graph})
    with patch("httpx.post", side_effect=fake_llm_post):
        client.post(f"/api/flows/{simple_flow['id']}/run", headers=headers, json={"input": "hello there"})
    simple_user_message = next(m["content"] for m in _seen_messages[-1] if m["role"] == "user")
    assert simple_user_message == "hello there"
    assert "Context:" not in simple_user_message
    print("[ok] a plain Input -> LLM chain is unaffected - no unnecessary framing added")

    print("\nAll LLM-node-context smoke tests passed.")


if __name__ == "__main__":
    main()
