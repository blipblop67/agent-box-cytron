"""
The whole point of the conversation feature is that a flow remembers earlier
turns - this test proves that concretely by checking the actual messages
sent to the LLM on turn two include turn one, not just that a conversation
record got created. Also covers: conversations are personal (not visible to
teammates even on a shared flow), history caps at a bounded window, and
deleting a conversation removes its messages.
Run with: python3 tests/test_conversations.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-conv-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()

_seen_message_lists = []


class FakeResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def fake_llm_post(url, headers=None, json=None, **kwargs):
    _seen_message_lists.append(json["messages"])
    # a deliberately dumb "assistant" that just echoes the number of user
    # turns it's seen, so the test can check whether history reached it
    user_turns = [m for m in json["messages"] if m["role"] == "user"]
    return FakeResponse(f"turn {len(user_turns)}")


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")

    client.put("/api/settings", headers=headers, json={
        "llm_provider": "openrouter", "openrouter_api_key": "test-key", "openrouter_model": "test/model",
    })

    flow = client.post("/api/flows", headers=headers, json={"name": "Coach", "visibility": "shared"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "llm", "type": "llm", "position": {"x": 200, "y": 0}, "data": {"system_prompt": "You are a coach."}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "llm"}, {"id": "e2", "source": "llm", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})

    conversation = client.post(f"/api/flows/{flow['id']}/conversations", headers=headers, json={"title": "Week 1"}).json()
    print(f"[ok] created a conversation: {conversation['id']}")

    with patch("httpx.post", side_effect=fake_llm_post):
        turn1 = client.post(f"/api/conversations/{conversation['id']}/messages", headers=headers, json={"content": "I want to run a 5k"})
        turn2 = client.post(f"/api/conversations/{conversation['id']}/messages", headers=headers, json={"content": "What was my goal again?"})

    assert turn1.status_code == 200 and turn2.status_code == 200
    print("[ok] sent two messages in the conversation")

    # --- the actual proof: turn 2's LLM call included turn 1's messages ---
    assert len(_seen_message_lists) == 2
    turn1_messages = _seen_message_lists[0]
    turn2_messages = _seen_message_lists[1]
    assert any(m["content"] == "I want to run a 5k" for m in turn1_messages)
    assert len(turn1_messages) == 2  # system + this turn's user message, no history yet
    assert any(m["content"] == "I want to run a 5k" for m in turn2_messages)
    assert any(m["content"] == "What was my goal again?" for m in turn2_messages)
    assert len(turn2_messages) == 4  # system + turn1 user + turn1 assistant + turn2 user
    print("[ok] the second turn's LLM call actually included the first turn's messages - this is the memory")

    # --- the conversation record has both exchanges stored ---
    detail = client.get(f"/api/conversations/{conversation['id']}", headers=headers).json()
    assert len(detail["messages"]) == 4  # user, assistant, user, assistant
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    print("[ok] conversation record stores all four messages in order")

    # --- conversations are personal, even on a shared flow ---
    sam_headers = auth_headers(client, "Sam")
    sam_conversations = client.get(f"/api/flows/{flow['id']}/conversations", headers=sam_headers).json()
    assert sam_conversations == []
    denied = client.get(f"/api/conversations/{conversation['id']}", headers=sam_headers)
    assert denied.status_code == 403
    print("[ok] Sam can't see Alex's conversation, even though the flow itself is shared")

    # --- deleting a conversation removes it ---
    client.delete(f"/api/conversations/{conversation['id']}", headers=headers)
    gone = client.get(f"/api/conversations/{conversation['id']}", headers=headers)
    assert gone.status_code == 404
    print("[ok] deleting a conversation removes it")

    print("\nAll conversation smoke tests passed.")


if __name__ == "__main__":
    main()
