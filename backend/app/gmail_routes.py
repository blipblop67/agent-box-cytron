"""
Direct Gmail action endpoints - send / list / read / reply - for manual
use and testing outside of a flow. A flow's Email node goes through
flow_engine.py directly rather than these; this router exists as a plain
API surface over gmail_client.py, which does all the actual work and is
where the real logic (and its docstring explaining the auth model) lives.

There's no per-user "connect" step anymore - Gmail authenticates entirely
through the hub-wide Google service account (see service_account_auth.py
and hub_settings.py). `impersonate` (a Workspace email) is required in
practice, since a plain service account has no inbox of its own.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import gmail_client, service_account_auth
from .auth import get_current_user

router = APIRouter(prefix="/email", tags=["email"])


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    impersonate: str | None = None


@router.post("/send")
def send(body: SendEmailRequest, user: dict = Depends(get_current_user)):
    try:
        return gmail_client.send_email(to=body.to, subject=body.subject, body=body.body, impersonate=body.impersonate)
    except service_account_auth.ServiceAccountError as exc:
        raise HTTPException(400, str(exc))


@router.get("/messages")
def list_messages(q: str = "", max_results: int = 10, impersonate: str | None = None,
                   user: dict = Depends(get_current_user)):
    try:
        return gmail_client.list_messages(query=q, max_results=max_results, impersonate=impersonate)
    except service_account_auth.ServiceAccountError as exc:
        raise HTTPException(400, str(exc))


@router.get("/messages/{message_id}")
def get_message(message_id: str, impersonate: str | None = None, user: dict = Depends(get_current_user)):
    try:
        return gmail_client.get_message(message_id, impersonate=impersonate)
    except service_account_auth.ServiceAccountError as exc:
        raise HTTPException(400, str(exc))


class ReplyRequest(BaseModel):
    body: str
    impersonate: str | None = None


@router.post("/messages/{message_id}/reply")
def reply(message_id: str, body: ReplyRequest, user: dict = Depends(get_current_user)):
    try:
        return gmail_client.reply_to_message(message_id, body.body, impersonate=body.impersonate)
    except service_account_auth.ServiceAccountError as exc:
        raise HTTPException(400, str(exc))
