"""
Per-user Telegram connection storage. Reuses the same oauth_credentials
table and encryption vault as Gmail/Drive even though this isn't OAuth - the
shape (user_id, provider, an encrypted secret, a human-readable label) fits
just as well, and it's one table/vault to reason about instead of two.

Connecting is two steps, not one: save the bot token, then link a chat id
(found by asking the person to message their new bot once). `chat_id` is
None between those two steps.
"""
import json

from . import crypto_vault, db

PROVIDER = "telegram"


def save_bot_token(user_id: str, bot_token: str, bot_username: str) -> None:
    payload = json.dumps({"bot_token": bot_token, "chat_id": None})
    db.upsert_oauth_credential(user_id, PROVIDER, crypto_vault.encrypt(payload), f"@{bot_username}")


def save_chat_id(user_id: str, chat_id: int) -> None:
    row = db.get_oauth_credential(user_id, PROVIDER)
    if row is None:
        raise LookupError("No Telegram bot connected for this user yet")
    stored = json.loads(crypto_vault.decrypt(row["encrypted_token"]))
    stored["chat_id"] = chat_id
    db.upsert_oauth_credential(user_id, PROVIDER, crypto_vault.encrypt(json.dumps(stored)), row["account_email"])


def get_credentials(user_id: str) -> dict | None:
    row = db.get_oauth_credential(user_id, PROVIDER)
    if row is None:
        return None
    stored = json.loads(crypto_vault.decrypt(row["encrypted_token"]))
    return {"bot_token": stored["bot_token"], "chat_id": stored.get("chat_id"), "bot_username": row["account_email"]}


def get_connection_status(user_id: str) -> dict | None:
    creds = get_credentials(user_id)
    if creds is None:
        return None
    return {
        "connected": True,
        "bot_username": creds["bot_username"],
        "chat_linked": creds["chat_id"] is not None,
    }


def disconnect(user_id: str) -> None:
    db.delete_oauth_credential(user_id, PROVIDER)
