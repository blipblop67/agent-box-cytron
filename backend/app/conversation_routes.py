"""
Conversations give a flow memory across multiple messages, unlike a plain
Run which is always a fresh one-shot. Personal, not shared - like chat
history, each person's conversations with a flow are their own, even for a
flow the whole team can see and run.

A conversation just accumulates {role, content} turns; sending a new
message replays the flow with everything said so far handed to every LLM
node in it (see flow_engine.run_flow's `history` parameter), then appends
both the new user message and the flow's final output as the reply.
"""
import json

from fastapi import APIRouter, Depends, HTTPException

from . import db, flow_engine
from .auth import get_current_user
from .models import (
    ConversationCreate,
    ConversationDetailOut,
    ConversationMessageOut,
    ConversationOut,
    ConversationSendMessage,
    ConversationSendResponse,
)

router = APIRouter(tags=["conversations"])

MAX_HISTORY_MESSAGES = 40  # keeps context bounded on a long-running conversation


def _require_flow_access(flow_id: str, user: dict):
    flow = db.get_flow(flow_id)
    if flow is None:
        raise HTTPException(404, "Flow not found")
    is_admin = user["role"] == "admin"
    if not db.user_can_access_flow(flow, user["id"], is_admin=is_admin):
        raise HTTPException(403, "This flow is private to another team member")
    return flow


def _require_conversation_access(conversation_id: str, user: dict) -> dict:
    conversation = db.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    # conversations are personal - not even an admin reads someone else's
    if conversation["user_id"] != user["id"]:
        raise HTTPException(403, "This is someone else's conversation")
    return conversation


@router.post("/flows/{flow_id}/conversations", response_model=ConversationOut)
def create_conversation(flow_id: str, body: ConversationCreate, user: dict = Depends(get_current_user)):
    _require_flow_access(flow_id, user)
    conversation_id = db.create_conversation(flow_id, user["id"], body.title)
    return ConversationOut(**dict(db.get_conversation(conversation_id)))


@router.get("/flows/{flow_id}/conversations", response_model=list[ConversationOut])
def list_conversations(flow_id: str, user: dict = Depends(get_current_user)):
    _require_flow_access(flow_id, user)
    return [ConversationOut(**dict(c)) for c in db.list_conversations(flow_id, user["id"])]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(conversation_id: str, user: dict = Depends(get_current_user)):
    conversation = _require_conversation_access(conversation_id, user)
    messages = [ConversationMessageOut(**dict(m)) for m in db.list_conversation_messages(conversation_id)]
    return ConversationDetailOut(**dict(conversation), messages=messages)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user: dict = Depends(get_current_user)):
    _require_conversation_access(conversation_id, user)
    db.delete_conversation(conversation_id)
    return {"deleted": conversation_id}


@router.post("/conversations/{conversation_id}/messages", response_model=ConversationSendResponse)
def send_message(conversation_id: str, body: ConversationSendMessage, user: dict = Depends(get_current_user)):
    conversation = _require_conversation_access(conversation_id, user)
    flow = _require_flow_access(conversation["flow_id"], user)

    prior = db.list_conversation_messages(conversation_id)
    history = [{"role": m["role"], "content": m["content"]} for m in prior][-MAX_HISTORY_MESSAGES:]

    graph = json.loads(flow["graph_json"])
    try:
        result = flow_engine.run_flow(graph, body.content, user["id"], history=history)
    except flow_engine.FlowError as exc:
        raise HTTPException(400, {"node_id": exc.node_id, "message": str(exc)})

    user_message_id = db.add_conversation_message(conversation_id, "user", body.content)
    assistant_message_id = db.add_conversation_message(conversation_id, "assistant", result["output"])
    db.touch_conversation(conversation_id)

    user_row = next(m for m in db.list_conversation_messages(conversation_id) if m["id"] == user_message_id)
    assistant_row = next(m for m in db.list_conversation_messages(conversation_id) if m["id"] == assistant_message_id)

    return ConversationSendResponse(
        user_message=ConversationMessageOut(**dict(user_row)),
        assistant_message=ConversationMessageOut(**dict(assistant_row)),
        trace=result["trace"],
    )
