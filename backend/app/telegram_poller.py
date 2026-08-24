"""
Makes "message the bot and get a reply, from anywhere, without touching
the Pi" actually true. A Telegram trigger pairs a bot with a flow; this
module is what a recurring background job (see scheduler.py) calls to
check every enabled trigger for new messages, run the flow, and send the
reply back - all without anyone clicking Run.

check_all_triggers() is a single synchronous function precisely so it can
be unit-tested directly (call it, assert on what happened) rather than
needing to wait on a real background scheduler tick, which would make
tests slow and flaky. The scheduler just calls this on an interval.
"""
import json
import logging

from . import db, flow_engine, telegram_client, telegram_tokens

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 40  # same cap conversation_routes.py uses for Chat


def check_all_triggers() -> None:
    for trigger in db.list_enabled_telegram_triggers():
        try:
            _check_one_trigger(trigger)
        except Exception:  # noqa: BLE001 - one bad trigger must never stop the others from being checked
            logger.exception("Telegram trigger %s failed during polling", trigger["id"])


def _check_one_trigger(trigger) -> None:
    bot = db.get_telegram_bot(trigger["bot_id"])
    if bot is None or not bot["chat_linked"]:
        return  # bot was deleted or unlinked out from under an active trigger - nothing to do

    creds = telegram_tokens.get_credentials(trigger["bot_id"])
    if creds is None or creds["chat_id"] is None:
        return

    if trigger["last_update_id"] is None:
        # first time this trigger has ever been checked - establish a
        # starting point rather than replaying the bot's entire backlog
        # into what's supposed to be a live conversation
        latest = telegram_client.latest_update_id(creds["bot_token"])
        db.set_telegram_trigger_last_update_id(trigger["id"], latest or 0)
        return

    new_messages = telegram_client.poll_new_messages(creds["bot_token"], trigger["last_update_id"])
    if not new_messages:
        return

    own_chat_messages = [m for m in new_messages if m["chat_id"] == creds["chat_id"]]

    # always advance past every update seen, even ones from a different
    # chat than the linked one, so they're never re-delivered on the next poll
    db.set_telegram_trigger_last_update_id(trigger["id"], max(m["update_id"] for m in new_messages))

    for message in own_chat_messages:
        _handle_message(trigger, creds, message["text"])


def _handle_message(trigger, creds: dict, incoming_text: str) -> None:
    flow = db.get_flow(trigger["flow_id"])
    if flow is None:
        db.create_telegram_trigger_run(
            trigger["id"], incoming_text, None, "error", "The flow this trigger points at no longer exists",
        )
        return

    prior = db.list_conversation_messages(trigger["conversation_id"])
    history = [{"role": m["role"], "content": m["content"]} for m in prior][-MAX_HISTORY_MESSAGES:]

    graph = json.loads(flow["graph_json"])
    try:
        result = flow_engine.run_flow(graph, incoming_text, trigger["created_by"], history=history)
        reply_text = result["output"]
    except flow_engine.FlowError as exc:
        db.create_telegram_trigger_run(trigger["id"], incoming_text, None, "error", str(exc))
        return

    db.add_conversation_message(trigger["conversation_id"], "user", incoming_text)
    db.add_conversation_message(trigger["conversation_id"], "assistant", reply_text)
    db.touch_conversation(trigger["conversation_id"])

    try:
        telegram_client.send_message(creds["bot_token"], creds["chat_id"], reply_text)
    except telegram_client.TelegramApiError as exc:
        db.create_telegram_trigger_run(trigger["id"], incoming_text, reply_text, "error", f"Reply failed to send: {exc}")
        return

    db.create_telegram_trigger_run(trigger["id"], incoming_text, reply_text, "success", None)
