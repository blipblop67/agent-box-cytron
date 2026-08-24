"""
A Telegram trigger pairs one flow with one bot: whenever that bot's linked
chat gets a new message, the flow runs automatically (with the running
conversation's history, like Chat) and the flow's output is sent back as
the reply - no session, no clicking Run, no needing to be anywhere near
the hub. The actual polling/running happens in telegram_poller.py, called
on a fixed interval by scheduler.py; this file is just the CRUD for
setting a trigger up.

A bot can only be wired to one trigger at a time - if two different flows
both listened on the same bot, an incoming message would be ambiguous
about which one should answer it.
"""
from fastapi import APIRouter, Depends, HTTPException

from . import db
from .auth import get_current_user
from .models import TelegramTriggerCreate, TelegramTriggerOut, TelegramTriggerRunOut, TelegramTriggerUpdate

router = APIRouter(tags=["telegram-triggers"])


def _require_flow_access(flow_id: str, user: dict):
    flow = db.get_flow(flow_id)
    if flow is None:
        raise HTTPException(404, "Flow not found")
    is_admin = user["role"] == "admin"
    if not db.user_can_access_flow(flow, user["id"], is_admin=is_admin):
        raise HTTPException(403, "This flow is private to another team member")
    return flow


def _require_bot_access(bot_id: str, user: dict):
    bot = db.get_telegram_bot(bot_id)
    if bot is None:
        raise HTTPException(404, "No such bot")
    is_admin = user["role"] == "admin"
    if not db.user_can_access_telegram_bot(bot, user["id"], is_admin=is_admin):
        raise HTTPException(403, "This bot is private to another team member")
    return bot


def _trigger_out(trigger) -> TelegramTriggerOut:
    bot = db.get_telegram_bot(trigger["bot_id"])
    return TelegramTriggerOut(
        id=trigger["id"], flow_id=trigger["flow_id"], bot_id=trigger["bot_id"],
        bot_name=bot["name"] if bot else "(deleted bot)", conversation_id=trigger["conversation_id"],
        enabled=bool(trigger["enabled"]), created_by=trigger["created_by"], created_at=trigger["created_at"],
    )


@router.get("/flows/{flow_id}/telegram-trigger", response_model=TelegramTriggerOut | None)
def get_trigger(flow_id: str, user: dict = Depends(get_current_user)):
    _require_flow_access(flow_id, user)
    trigger = db.get_telegram_trigger_for_flow(flow_id)
    return _trigger_out(trigger) if trigger else None


@router.post("/flows/{flow_id}/telegram-trigger", response_model=TelegramTriggerOut)
def create_trigger(flow_id: str, body: TelegramTriggerCreate, user: dict = Depends(get_current_user)):
    _require_flow_access(flow_id, user)
    bot = _require_bot_access(body.bot_id, user)
    if not bot["chat_linked"]:
        raise HTTPException(400, "Finish linking this bot on the Connections page before using it as a trigger")

    if db.get_telegram_trigger_for_flow(flow_id) is not None:
        raise HTTPException(400, "This flow already has a trigger - remove it before adding a new one")

    existing_for_bot = db.get_telegram_trigger_for_bot(body.bot_id)
    if existing_for_bot is not None:
        other_flow = db.get_flow(existing_for_bot["flow_id"])
        other_name = other_flow["name"] if other_flow else "another flow"
        raise HTTPException(400, f"'{bot['name']}' is already wired to '{other_name}' - remove that trigger first")

    conversation_id = db.create_conversation(flow_id, user["id"], f"Telegram: {bot['name']}")
    trigger_id = db.create_telegram_trigger(flow_id, body.bot_id, conversation_id, user["id"])
    return _trigger_out(db.get_telegram_trigger(trigger_id))


@router.patch("/telegram-triggers/{trigger_id}", response_model=TelegramTriggerOut)
def update_trigger(trigger_id: str, body: TelegramTriggerUpdate, user: dict = Depends(get_current_user)):
    trigger = db.get_telegram_trigger(trigger_id)
    if trigger is None:
        raise HTTPException(404, "No such trigger")
    _require_flow_access(trigger["flow_id"], user)
    db.set_telegram_trigger_enabled(trigger_id, body.enabled)
    return _trigger_out(db.get_telegram_trigger(trigger_id))


@router.delete("/telegram-triggers/{trigger_id}")
def delete_trigger(trigger_id: str, user: dict = Depends(get_current_user)):
    trigger = db.get_telegram_trigger(trigger_id)
    if trigger is None:
        raise HTTPException(404, "No such trigger")
    _require_flow_access(trigger["flow_id"], user)
    db.delete_telegram_trigger(trigger_id)
    return {"deleted": trigger_id}


@router.get("/telegram-triggers/{trigger_id}/runs", response_model=list[TelegramTriggerRunOut])
def list_trigger_runs(trigger_id: str, user: dict = Depends(get_current_user)):
    trigger = db.get_telegram_trigger(trigger_id)
    if trigger is None:
        raise HTTPException(404, "No such trigger")
    _require_flow_access(trigger["flow_id"], user)
    return [TelegramTriggerRunOut(**dict(r)) for r in db.list_telegram_trigger_runs(trigger_id)]
