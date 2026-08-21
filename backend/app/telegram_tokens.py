"""
Telegram bot storage. Unlike Gmail/Drive (one personal connection per user),
a bot is a named, ownable resource - shared or private, same as a knowledge
base - so different flows can be wired to different bots regardless of who
happens to run them. See db.py's telegram_bots table and access-control
functions, which this module is a thin wrapper around for the token
encrypt/decrypt bookkeeping.

Connecting a bot is two steps, not one: save the token, then link a chat id
(found by asking the person to message their new bot once). `chat_id` is
None between those two steps.
"""
import json

from . import crypto_vault, db


def create_bot(name: str, owner_id: str, visibility: str, bot_token: str, bot_username: str) -> str:
    payload = json.dumps({"bot_token": bot_token, "chat_id": None})
    return db.create_telegram_bot(name, owner_id, visibility, crypto_vault.encrypt(payload), bot_username)


def save_chat_id(bot_id: str, chat_id: int) -> None:
    row = db.get_telegram_bot(bot_id)
    if row is None:
        raise LookupError("No such bot")
    stored = json.loads(crypto_vault.decrypt(row["encrypted_token"]))
    stored["chat_id"] = chat_id
    db.update_telegram_bot_token(bot_id, crypto_vault.encrypt(json.dumps(stored)), chat_linked=True)


def get_credentials(bot_id: str) -> dict | None:
    row = db.get_telegram_bot(bot_id)
    if row is None:
        return None
    stored = json.loads(crypto_vault.decrypt(row["encrypted_token"]))
    return {"bot_token": stored["bot_token"], "chat_id": stored.get("chat_id"), "bot_username": row["bot_username"]}


def bot_out(row) -> dict:
    """The shape returned to the frontend - never the token itself."""
    return {
        "id": row["id"],
        "name": row["name"],
        "owner_id": row["owner_id"],
        "visibility": row["visibility"],
        "bot_username": row["bot_username"],
        "chat_linked": bool(row["chat_linked"]),
        "created_at": row["created_at"],
    }
