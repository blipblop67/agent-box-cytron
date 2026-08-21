"""
Exercises the new Telegram model: bots are named, ownable resources (shared
or private) rather than one bot per user - so the actual point of the
redesign, different flows using different bots regardless of who runs them,
gets a real end-to-end test, not just CRUD on a single connection.
Run with: python3 tests/test_telegram.py
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

BOT_A_TOKEN = "111:SUPPORT-BOT-TOKEN"
BOT_B_TOKEN = "222:SALES-BOT-TOKEN"
CHAT_A = 111000
CHAT_B = 222000

# Simulates each bot having received a message, between create and link
_pending_updates = {BOT_A_TOKEN: [], BOT_B_TOKEN: []}


class FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def json(self):
        return self._json


def fake_post(url, json=None, **kwargs):
    for token, username in ((BOT_A_TOKEN, "support_bot"), (BOT_B_TOKEN, "sales_bot")):
        if url.startswith(f"https://api.telegram.org/bot{token}/"):
            method = url.rsplit("/", 1)[-1]
            if method == "getMe":
                return FakeResponse({"ok": True, "result": {"id": 1, "username": username, "is_bot": True}})
            if method == "getUpdates":
                return FakeResponse({"ok": True, "result": list(_pending_updates[token])})
            if method == "sendMessage":
                return FakeResponse({"ok": True, "result": {"message_id": 1, "chat": {"id": json["chat_id"]}, "text": json["text"]}})
    raise AssertionError(f"unexpected Telegram call: {url}")


def fake_post_invalid_token(url, json=None, **kwargs):
    if url.endswith("/getMe"):
        return FakeResponse({"ok": False, "error_code": 401, "description": "Unauthorized"})
    raise AssertionError("shouldn't get here with an invalid token")


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")
    sam_headers = auth_headers(client, "Sam")

    # --- rejects an invalid token up front ---
    with patch("httpx.post", side_effect=fake_post_invalid_token):
        bad = client.post("/api/telegram/bots", headers=headers, json={"name": "Bad Bot", "bot_token": "nope"})
    assert bad.status_code == 400 and "valid bot token" in bad.text
    print("[ok] an invalid bot token is rejected immediately")

    assert client.get("/api/telegram/bots", headers=headers).json() == []

    # --- Alex creates two bots: one shared, one private ---
    with patch("httpx.post", side_effect=fake_post):
        support_bot = client.post("/api/telegram/bots", headers=headers, json={
            "name": "Support Bot", "bot_token": BOT_A_TOKEN, "visibility": "shared",
        }).json()
        sales_bot = client.post("/api/telegram/bots", headers=headers, json={
            "name": "Sales Bot", "bot_token": BOT_B_TOKEN, "visibility": "private",
        }).json()
    assert support_bot["chat_linked"] is False and support_bot["bot_username"] == "support_bot"
    assert sales_bot["chat_linked"] is False
    print(f"[ok] created two bots: {support_bot['id']} (shared), {sales_bot['id']} (private)")

    # --- Sam sees the shared bot but not the private one ---
    sam_bots = client.get("/api/telegram/bots", headers=sam_headers).json()
    sam_bot_ids = {b["id"] for b in sam_bots}
    assert support_bot["id"] in sam_bot_ids
    assert sales_bot["id"] not in sam_bot_ids
    print("[ok] Sam sees the shared bot but not Alex's private one")

    # --- linking before any message exists gives a clear instruction ---
    with patch("httpx.post", side_effect=fake_post):
        too_early = client.post(f"/api/telegram/bots/{support_bot['id']}/link", headers=headers)
    assert too_early.status_code == 400 and "No messages found" in too_early.text
    print("[ok] linking before any message exists gives a clear instruction")

    # --- someone messages each bot, then both get linked ---
    _pending_updates[BOT_A_TOKEN].append({
        "update_id": 1, "message": {"chat": {"id": CHAT_A}, "text": "hi", "date": 1, "from": {"first_name": "Alex"}},
    })
    _pending_updates[BOT_B_TOKEN].append({
        "update_id": 1, "message": {"chat": {"id": CHAT_B}, "text": "hi", "date": 1, "from": {"first_name": "Alex"}},
    })
    with patch("httpx.post", side_effect=fake_post):
        linked_a = client.post(f"/api/telegram/bots/{support_bot['id']}/link", headers=headers).json()
        linked_b = client.post(f"/api/telegram/bots/{sales_bot['id']}/link", headers=headers).json()
    assert linked_a["chat_linked"] is True and linked_b["chat_linked"] is True
    print("[ok] both bots linked to their own chat")

    # --- a non-owner can't delete or relink someone else's bot ---
    forbidden_delete = client.delete(f"/api/telegram/bots/{sales_bot['id']}", headers=sam_headers)
    assert forbidden_delete.status_code in (403, 404)  # 404 if Sam can't even see the private bot
    print("[ok] a non-owner can't delete someone else's bot")

    # --- THE ACTUAL POINT: two flows, two different bots, proven by which token each call used ---
    calls = []

    def recording_post(url, json=None, **kwargs):
        calls.append(url)
        return fake_post(url, json=json, **kwargs)

    support_flow = client.post("/api/flows", headers=headers, json={"name": "Customer Support"}).json()
    sales_flow = client.post("/api/flows", headers=headers, json={"name": "Sales Outreach"}).json()

    def telegram_graph(bot_id):
        return {
            "nodes": [
                {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
                {"id": "tg", "type": "telegram", "position": {"x": 200, "y": 0}, "data": {"action": "send", "bot_id": bot_id}},
                {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
            ],
            "edges": [{"id": "e1", "source": "in", "target": "tg"}, {"id": "e2", "source": "tg", "target": "out"}],
        }

    client.put(f"/api/flows/{support_flow['id']}", headers=headers, json={"graph": telegram_graph(support_bot["id"])})
    client.put(f"/api/flows/{sales_flow['id']}", headers=headers, json={"graph": telegram_graph(sales_bot["id"])})

    with patch("httpx.post", side_effect=recording_post):
        result_a = client.post(f"/api/flows/{support_flow['id']}/run", headers=headers, json={"input": "A customer needs help"})
        result_b = client.post(f"/api/flows/{sales_flow['id']}/run", headers=headers, json={"input": "New lead came in"})

    assert result_a.status_code == 200 and result_b.status_code == 200
    assert "Support Bot" in result_a.json()["output"] and "support_bot" in result_a.json()["output"]
    assert "Sales Bot" in result_b.json()["output"] and "sales_bot" in result_b.json()["output"]
    assert any(BOT_A_TOKEN in c for c in calls)
    assert any(BOT_B_TOKEN in c for c in calls)
    print(f"[ok] Customer Support flow used Support Bot: \"{result_a.json()['output']}\"")
    print(f"[ok] Sales Outreach flow used Sales Bot: \"{result_b.json()['output']}\"")
    print("[ok] confirmed via the actual mocked HTTP calls that each flow hit a different bot token")

    # --- read via the per-bot REST endpoint too ---
    _pending_updates[BOT_A_TOKEN].append({
        "update_id": 2, "message": {"chat": {"id": CHAT_A}, "text": "reply", "date": 2, "from": {"first_name": "Alex"}},
    })
    with patch("httpx.post", side_effect=fake_post):
        msgs = client.get(f"/api/telegram/bots/{support_bot['id']}/messages", headers=headers).json()
    assert any(m["text"] == "reply" for m in msgs)
    print("[ok] read recent messages via the per-bot REST endpoint")

    # --- owner can delete their own bot; it disappears from the list ---
    client.delete(f"/api/telegram/bots/{sales_bot['id']}", headers=headers)
    remaining = client.get("/api/telegram/bots", headers=headers).json()
    assert not any(b["id"] == sales_bot["id"] for b in remaining)
    print("[ok] owner deleted their own bot")

    print("\nAll Telegram smoke tests passed.")


if __name__ == "__main__":
    main()
