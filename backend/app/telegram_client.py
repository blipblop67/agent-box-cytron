"""
Thin wrapper around the Telegram Bot API - a bot token, not OAuth, is how
Telegram integrations authenticate. Someone creates their own bot via
@BotFather, pastes the token in here, and this hub uses it to message them
(and read messages sent to it) on their behalf.
"""
import httpx

API_BASE = "https://api.telegram.org/bot{token}"


class TelegramApiError(Exception):
    pass


def _call(bot_token: str, method: str, **params) -> dict:
    resp = httpx.post(f"{API_BASE.format(token=bot_token)}/{method}", json=params, timeout=30)
    data = resp.json()
    if not data.get("ok"):
        raise TelegramApiError(data.get("description", f"Telegram API call to {method} failed"))
    return data["result"]


def get_me(bot_token: str) -> dict:
    """Validates the token and returns the bot's own identity - used right
    when someone pastes a token in, so a typo fails immediately and clearly
    rather than silently on the first real send."""
    return _call(bot_token, "getMe")


def find_latest_chat_id(bot_token: str) -> int | None:
    """After pasting a token, the person is told to message their new bot
    once. This looks at the bot's pending updates and returns the chat id of
    the most recent message - that's the "link my chat" step. Returns None
    if nobody has messaged the bot yet."""
    updates = _call(bot_token, "getUpdates")
    for update in reversed(updates):
        message = update.get("message") or update.get("channel_post")
        if message and "chat" in message:
            return message["chat"]["id"]
    return None


def send_message(bot_token: str, chat_id: int, text: str) -> dict:
    return _call(bot_token, "sendMessage", chat_id=chat_id, text=text)


def get_recent_messages(bot_token: str, chat_id: int, limit: int = 10) -> list[dict]:
    """Recent *incoming* messages from this chat - used by a Telegram node's
    'read' action. getUpdates only surfaces messages the bot hasn't already
    been asked about, which is a reasonable fit for "what's new" style reads."""
    updates = _call(bot_token, "getUpdates")
    messages = []
    for update in updates:
        message = update.get("message")
        if message and message.get("chat", {}).get("id") == chat_id and "text" in message:
            messages.append({
                "text": message["text"],
                "date": message["date"],
                "from": message.get("from", {}).get("first_name", "Unknown"),
            })
    return messages[-limit:]
