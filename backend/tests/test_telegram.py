"""
Exercises the whole Telegram integration - connect a bot token, link a chat
by "sending" the bot a message, send/read through it, and use it from inside
a real flow. Mocks only Telegram's HTTP API. Run with:
    python3 tests/test_telegram.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-telegram-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()

BOT_TOKEN = "123456:FAKE-BOT-TOKEN"
CHAT_ID = 999888777

# Simulates the person messaging their bot once, between /connect and /link
_pending_updates = []


class FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def json(self):
        return self._json


def fake_post(url, json=None, **kwargs):
    assert url.startswith(f"https://api.telegram.org/bot{BOT_TOKEN}/")
    method = url.rsplit("/", 1)[-1]

    if method == "getMe":
        return FakeResponse({"ok": True, "result": {"id": 42, "username": "my_agent_hub_bot", "is_bot": True}})

    if method == "getUpdates":
        return FakeResponse({"ok": True, "result": list(_pending_updates)})

    if method == "sendMessage":
        return FakeResponse({"ok": True, "result": {"message_id": 1, "chat": {"id": json["chat_id"]}, "text": json["text"]}})

    raise AssertionError(f"unexpected Telegram method {method}")


def fake_post_invalid_token(url, json=None, **kwargs):
    if url.endswith("/getMe"):
        return FakeResponse({"ok": False, "error_code": 401, "description": "Unauthorized"})
    raise AssertionError("shouldn't get here with an invalid token")


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")

    # --- rejects an invalid token up front ---
    with patch("httpx.post", side_effect=fake_post_invalid_token):
        bad = client.post("/api/telegram/connect", headers=headers, json={"bot_token": "nope"})
    assert bad.status_code == 400 and "valid bot token" in bad.text
    print("[ok] an invalid bot token is rejected immediately")

    assert client.get("/api/telegram/status", headers=headers).json() == {"connected": False}

    # --- step 1: save a valid token ---
    with patch("httpx.post", side_effect=fake_post):
        connected = client.post("/api/telegram/connect", headers=headers, json={"bot_token": BOT_TOKEN}).json()
    assert connected["connected"] is True
    assert connected["chat_linked"] is False
    assert connected["bot_username"] == "@my_agent_hub_bot"
    print("[ok] bot token saved, not yet linked to a chat")

    # --- trying to link before the person has messaged the bot ---
    with patch("httpx.post", side_effect=fake_post):
        too_early = client.post("/api/telegram/link", headers=headers)
    assert too_early.status_code == 400 and "No messages found" in too_early.text
    print("[ok] linking before any message exists gives a clear instruction")

    # --- the person messages their bot ---
    _pending_updates.append({
        "update_id": 1,
        "message": {"chat": {"id": CHAT_ID}, "text": "hi", "date": 1234567890, "from": {"first_name": "Alex"}},
    })

    # --- step 2: link succeeds now ---
    with patch("httpx.post", side_effect=fake_post):
        linked = client.post("/api/telegram/link", headers=headers).json()
    assert linked["chat_linked"] is True
    print("[ok] linked successfully once a message exists")

    # --- send / read through the REST endpoints ---
    with patch("httpx.post", side_effect=fake_post):
        sent = client.post("/api/telegram/send", headers=headers, json={"text": "hello from the hub"})
        assert sent.status_code == 200
        print("[ok] sent a message via /api/telegram/send")

        _pending_updates.append({
            "update_id": 2,
            "message": {"chat": {"id": CHAT_ID}, "text": "reply from Alex", "date": 1234567999, "from": {"first_name": "Alex"}},
        })
        msgs = client.get("/api/telegram/messages", headers=headers).json()
        assert any(m["text"] == "reply from Alex" for m in msgs)
        print(f"[ok] read {len(msgs)} recent message(s) via /api/telegram/messages")

    # --- a flow with a Telegram send node ---
    flow = client.post("/api/flows", headers=headers, json={"name": "Notify me"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "tg", "type": "telegram", "position": {"x": 200, "y": 0}, "data": {"action": "send"}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "tg"}, {"id": "e2", "source": "tg", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})
    with patch("httpx.post", side_effect=fake_post):
        result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": "Build finished!"})
    assert result.status_code == 200, result.text
    assert "Sent to Telegram" in result.json()["output"]
    print(f"[ok] flow with a Telegram node ran: \"{result.json()['output']}\"")

    # --- disconnect ---
    client.delete("/api/telegram/auth", headers=headers)
    assert client.get("/api/telegram/status", headers=headers).json() == {"connected": False}
    print("[ok] disconnect works")

    print("\nAll Telegram smoke tests passed.")


if __name__ == "__main__":
    main()
