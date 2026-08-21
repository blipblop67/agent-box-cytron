"""
Telegram integration: create a named bot (paste its token, message it once
to link a chat), then a Telegram node in any flow you can see picks which
bot to use from a dropdown - same shared/private visibility model as
knowledge bases, so different agents can be wired to different bots
regardless of who happens to click Run.
"""
from fastapi import APIRouter, Depends, HTTPException

from . import db, telegram_client, telegram_tokens
from .auth import get_current_user
from .models import TelegramBotCreate, TelegramBotOut, TelegramBotUpdate, TelegramSendRequest

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _require_bot_access(bot_id: str, user: dict, require_owner: bool = False) -> dict:
    bot = db.get_telegram_bot(bot_id)
    if bot is None:
        raise HTTPException(404, "No such bot")
    is_admin = user["role"] == "admin"
    if require_owner:
        if not (is_admin or bot["owner_id"] == user["id"]):
            raise HTTPException(403, "Only the bot's owner (or a hub admin) can do this")
    elif not db.user_can_access_telegram_bot(bot, user["id"], is_admin=is_admin):
        raise HTTPException(403, "This bot is private to another team member")
    return bot


@router.get("/bots", response_model=list[TelegramBotOut])
def list_bots(user: dict = Depends(get_current_user)):
    is_admin = user["role"] == "admin"
    return [telegram_tokens.bot_out(b) for b in db.list_telegram_bots(user["id"], is_admin=is_admin)]


@router.post("/bots", response_model=TelegramBotOut)
def create_bot(body: TelegramBotCreate, user: dict = Depends(get_current_user)):
    try:
        info = telegram_client.get_me(body.bot_token)
    except telegram_client.TelegramApiError as exc:
        raise HTTPException(400, f"That doesn't look like a valid bot token: {exc}")
    bot_id = telegram_tokens.create_bot(body.name, user["id"], body.visibility, body.bot_token, info["username"])
    return telegram_tokens.bot_out(db.get_telegram_bot(bot_id))


@router.patch("/bots/{bot_id}", response_model=TelegramBotOut)
def update_bot(bot_id: str, body: TelegramBotUpdate, user: dict = Depends(get_current_user)):
    _require_bot_access(bot_id, user, require_owner=True)
    if body.name is not None:
        db.rename_telegram_bot(bot_id, body.name)
    if body.visibility is not None:
        db.set_telegram_bot_visibility(bot_id, body.visibility)
    return telegram_tokens.bot_out(db.get_telegram_bot(bot_id))


@router.post("/bots/{bot_id}/link", response_model=TelegramBotOut)
def link_bot(bot_id: str, user: dict = Depends(get_current_user)):
    """Find the chat id from whatever the person just sent this bot."""
    _require_bot_access(bot_id, user, require_owner=True)
    creds = telegram_tokens.get_credentials(bot_id)
    chat_id = telegram_client.find_latest_chat_id(creds["bot_token"])
    if chat_id is None:
        raise HTTPException(
            400,
            f"No messages found yet - open Telegram, search for {creds['bot_username']}, "
            f"send it any message, then try linking again.",
        )
    telegram_tokens.save_chat_id(bot_id, chat_id)
    telegram_client.send_message(creds["bot_token"], chat_id, "Linked! This bot is now connected to Agent Hub.")
    return telegram_tokens.bot_out(db.get_telegram_bot(bot_id))


@router.delete("/bots/{bot_id}")
def delete_bot(bot_id: str, user: dict = Depends(get_current_user)):
    _require_bot_access(bot_id, user, require_owner=True)
    db.delete_telegram_bot(bot_id)
    return {"deleted": bot_id}


@router.post("/bots/{bot_id}/send")
def send(bot_id: str, body: TelegramSendRequest, user: dict = Depends(get_current_user)):
    _require_bot_access(bot_id, user)
    creds = _require_linked(bot_id)
    return telegram_client.send_message(creds["bot_token"], creds["chat_id"], body.text)


@router.get("/bots/{bot_id}/messages")
def messages(bot_id: str, max_results: int = 10, user: dict = Depends(get_current_user)):
    _require_bot_access(bot_id, user)
    creds = _require_linked(bot_id)
    return telegram_client.get_recent_messages(creds["bot_token"], creds["chat_id"], limit=max_results)


def _require_linked(bot_id: str) -> dict:
    creds = telegram_tokens.get_credentials(bot_id)
    if creds is None or creds["chat_id"] is None:
        raise HTTPException(400, "This bot isn't fully linked yet - see the Connections page")
    return creds
