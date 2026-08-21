"""
Telegram integration: paste a bot token, message the bot once to link a
chat, then send/read through it. Each team member connects their own bot -
tokens stored per user_id, encrypted at rest (see crypto_vault.py). This is
what a "Telegram" tool node in the flow builder calls at agent run-time.
"""
from fastapi import APIRouter, Depends, HTTPException

from . import telegram_client, telegram_tokens
from .auth import get_current_user
from .models import TelegramConnectRequest, TelegramSendRequest

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.get("/status")
def status(user: dict = Depends(get_current_user)):
    return telegram_tokens.get_connection_status(user["id"]) or {"connected": False}


@router.post("/connect")
def connect(body: TelegramConnectRequest, user: dict = Depends(get_current_user)):
    """Step 1: validate the token against Telegram, save it. The chat isn't
    linked yet - that's a separate step once the person has messaged the bot."""
    try:
        bot = telegram_client.get_me(body.bot_token)
    except telegram_client.TelegramApiError as exc:
        raise HTTPException(400, f"That doesn't look like a valid bot token: {exc}")
    telegram_tokens.save_bot_token(user["id"], body.bot_token, bot["username"])
    return telegram_tokens.get_connection_status(user["id"])


@router.post("/link")
def link(user: dict = Depends(get_current_user)):
    """Step 2: find the chat id from whatever the person just sent their bot."""
    creds = telegram_tokens.get_credentials(user["id"])
    if creds is None:
        raise HTTPException(400, "Save a bot token first")
    chat_id = telegram_client.find_latest_chat_id(creds["bot_token"])
    if chat_id is None:
        raise HTTPException(
            400,
            f"No messages found yet - open Telegram, search for {creds['bot_username']}, "
            f"send it any message, then try linking again.",
        )
    telegram_tokens.save_chat_id(user["id"], chat_id)
    telegram_client.send_message(creds["bot_token"], chat_id, "Linked! This bot is now connected to Agent Hub.")
    return telegram_tokens.get_connection_status(user["id"])


@router.delete("/auth")
def disconnect(user: dict = Depends(get_current_user)):
    telegram_tokens.disconnect(user["id"])
    return {"disconnected": True}


def _require_linked(user_id: str) -> dict:
    creds = telegram_tokens.get_credentials(user_id)
    if creds is None or creds["chat_id"] is None:
        raise HTTPException(400, "Telegram isn't fully connected for this user yet - see the Connections page")
    return creds


@router.post("/send")
def send(body: TelegramSendRequest, user: dict = Depends(get_current_user)):
    creds = _require_linked(user["id"])
    return telegram_client.send_message(creds["bot_token"], creds["chat_id"], body.text)


@router.get("/messages")
def messages(max_results: int = 10, user: dict = Depends(get_current_user)):
    creds = _require_linked(user["id"])
    return telegram_client.get_recent_messages(creds["bot_token"], creds["chat_id"], limit=max_results)
