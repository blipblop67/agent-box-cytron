"""
The whole point of this feature: someone messages a Telegram bot and gets
a reply automatically - no clicking Run, no being at the hub - and can
have an actual back-and-forth, because the trigger remembers the
conversation the same way Chat does. This test proves it by calling the
poller directly (the same function scheduler.py calls on an interval),
never once calling a /run endpoint.

Also covers: a bot can only be wired to one trigger at a time, a disabled
trigger doesn't respond, and the first poll after enabling a trigger
doesn't replay old messages into the conversation.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-tgtrigger-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, telegram_poller  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()

BOT_TOKEN = "111:COACH-BOT-TOKEN"
CHAT_ID = 555000

# simulates Telegram's server-side update queue for this bot
_updates = []
_next_update_id = [100]  # Telegram update_ids are usually large/arbitrary, not starting at 0 or 1


def _queue_message(text: str):
    _next_update_id[0] += 1
    _updates.append({
        "update_id": _next_update_id[0],
        "message": {"chat": {"id": CHAT_ID}, "text": text, "date": 1, "from": {"first_name": "Alex"}},
    })


class FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


_seen_llm_messages = []


def fake_post(url, json=None, **kwargs):
    if url == f"https://api.telegram.org/bot{BOT_TOKEN}/getMe":
        return FakeResponse({"ok": True, "result": {"id": 1, "username": "coach_bot", "is_bot": True}})
    if url == f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates":
        offset = (json or {}).get("offset")
        if offset is None:
            return FakeResponse({"ok": True, "result": list(_updates)})
        visible = [u for u in _updates if u["update_id"] >= offset]
        return FakeResponse({"ok": True, "result": visible})
    if url == f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage":
        return FakeResponse({"ok": True, "result": {"message_id": 1, "chat": {"id": json["chat_id"]}, "text": json["text"]}})
    if url == "https://openrouter.ai/api/v1/chat/completions":
        _seen_llm_messages.append(json["messages"])
        user_turns = [m for m in json["messages"] if m["role"] == "user"]
        return FakeResponse({"choices": [{"message": {"content": f"Reply #{len(user_turns)}"}}]})
    raise AssertionError(f"unexpected call: {url}")


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")

    client.put("/api/settings", headers=headers, json={
        "llm_provider": "openrouter", "openrouter_api_key": "test-key", "openrouter_model": "test/model",
    })

    # --- set up: a bot, linked, and a simple chat-capable flow ---
    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_post):
        bot = client.post("/api/telegram/bots", headers=headers, json={
            "name": "Coach Bot", "bot_token": BOT_TOKEN, "visibility": "private",
        }).json()

    _queue_message("(someone said hi while linking)")
    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_post):
        bot = client.post(f"/api/telegram/bots/{bot['id']}/link", headers=headers).json()
    assert bot["chat_linked"] is True

    flow = client.post("/api/flows", headers=headers, json={"name": "Coach"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "llm", "type": "llm", "position": {"x": 200, "y": 0}, "data": {"system_prompt": "You are a coach."}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "llm"}, {"id": "e2", "source": "llm", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})

    # --- create the trigger ---
    trigger = client.post(f"/api/flows/{flow['id']}/telegram-trigger", headers=headers, json={"bot_id": bot["id"]}).json()
    assert trigger["enabled"] is True
    print(f"[ok] created a trigger wiring '{bot['name']}' to the flow")

    # --- a bot can't be double-wired ---
    other_flow = client.post("/api/flows", headers=headers, json={"name": "Other flow"}).json()
    dupe = client.post(f"/api/flows/{other_flow['id']}/telegram-trigger", headers=headers, json={"bot_id": bot["id"]})
    assert dupe.status_code == 400 and "already wired" in dupe.text
    print("[ok] the same bot can't be wired to a second flow's trigger")

    # --- first poll after creating the trigger establishes a baseline, doesn't reply to the old linking message ---
    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_post):
        telegram_poller.check_all_triggers()
    detail_before = client.get(f"/api/conversations/{trigger['conversation_id']}", headers=headers).json()
    assert detail_before["messages"] == []
    print("[ok] the first poll doesn't replay the old backlog into the conversation")

    # --- THE ACTUAL POINT: message the bot, poll, get a reply - with ZERO calls to /run ---
    _queue_message("I want to run a 5k")
    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_post):
        telegram_poller.check_all_triggers()

    detail = client.get(f"/api/conversations/{trigger['conversation_id']}", headers=headers).json()
    assert len(detail["messages"]) == 2
    assert detail["messages"][0]["role"] == "user" and detail["messages"][0]["content"] == "I want to run a 5k"
    assert detail["messages"][1]["role"] == "assistant" and detail["messages"][1]["content"] == "Reply #1"
    print("[ok] messaged the bot, polled, got a reply recorded in the conversation - no /run call involved")

    runs = client.get(f"/api/telegram-triggers/{trigger['id']}/runs", headers=headers).json()
    assert len(runs) == 1 and runs[0]["status"] == "success" and runs[0]["reply_text"] == "Reply #1"
    print("[ok] the run is logged with the incoming text and the reply")

    # --- a SECOND message: proves it's an actual back-and-forth, not just one-shot ---
    _queue_message("What was my goal again?")
    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_post):
        telegram_poller.check_all_triggers()

    turn2_messages = _seen_llm_messages[-1]
    turn2_user_content = [m["content"] for m in turn2_messages if m["role"] == "user"][-1]
    assert turn2_user_content == "What was my goal again?"
    assert any(m["content"] == "I want to run a 5k" for m in turn2_messages), "turn 1 missing from turn 2's history"
    print("[ok] the second message's LLM call included the first exchange - this is real back-and-forth memory")

    detail2 = client.get(f"/api/conversations/{trigger['conversation_id']}", headers=headers).json()
    assert len(detail2["messages"]) == 4
    print("[ok] conversation now has all four messages across two full turns")

    # --- disabling the trigger stops it from responding ---
    client.patch(f"/api/telegram-triggers/{trigger['id']}", headers=headers, json={"enabled": False})
    _queue_message("hello? anyone there?")
    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_post):
        telegram_poller.check_all_triggers()
    detail3 = client.get(f"/api/conversations/{trigger['conversation_id']}", headers=headers).json()
    assert len(detail3["messages"]) == 4  # unchanged - the disabled trigger never even looked
    print("[ok] a disabled trigger doesn't respond")

    print("\nAll Telegram trigger smoke tests passed.")


if __name__ == "__main__":
    main()
