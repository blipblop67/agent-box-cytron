"""
Two things live here now: the direct Gmail action endpoints (send / list /
read / reply) for manual use and testing - unchanged, still service-account
based - and the OAuth connection lifecycle (connect / disconnect / status)
for Path B, where someone personally signs into their own Gmail through
this hub's own Google Cloud project (see google_oauth.py's docstring for
why this exists alongside, not instead of, the service account model).

A flow's Email node goes through flow_engine.py directly rather than
either of these; this router exists as a plain API surface for the
Connections page and for manual testing.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from . import gmail_client, gmail_oauth, gmail_tokens, google_oauth, hub_settings, oauth_errors, oauth_state
from .auth import get_current_user

router = APIRouter(prefix="/email", tags=["email"])

CALLBACK_PATH = "/api/email/auth/callback"


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    impersonate: str | None = None


@router.post("/send")
def send(body: SendEmailRequest, user: dict = Depends(get_current_user)):
    try:
        return gmail_client.send_email(to=body.to, subject=body.subject, body=body.body, impersonate=body.impersonate)
    except gmail_client.GmailError as exc:
        raise HTTPException(400, str(exc))


@router.get("/messages")
def list_messages(q: str = "", max_results: int = 10, impersonate: str | None = None,
                   user: dict = Depends(get_current_user)):
    try:
        return gmail_client.list_messages(query=q, max_results=max_results, impersonate=impersonate)
    except gmail_client.GmailError as exc:
        raise HTTPException(400, str(exc))


@router.get("/messages/{message_id}")
def get_message(message_id: str, impersonate: str | None = None, user: dict = Depends(get_current_user)):
    try:
        return gmail_client.get_message(message_id, impersonate=impersonate)
    except gmail_client.GmailError as exc:
        raise HTTPException(400, str(exc))


class ReplyRequest(BaseModel):
    body: str
    impersonate: str | None = None


@router.post("/messages/{message_id}/reply")
def reply(message_id: str, body: ReplyRequest, user: dict = Depends(get_current_user)):
    try:
        return gmail_client.reply_to_message(message_id, body.body, impersonate=body.impersonate)
    except gmail_client.GmailError as exc:
        raise HTTPException(400, str(exc))


# ---- OAuth connection lifecycle (Path B - personal "Connect" flow) --------

@router.get("/status")
def status(user: dict = Depends(get_current_user)):
    return gmail_tokens.get_connection_status(user["id"]) or {"connected": False}


@router.get("/auth/start")
def auth_start(request: Request, user: dict = Depends(get_current_user)):
    client_id, client_secret = hub_settings.get_google_oauth_client()
    if not client_id or not client_secret:
        raise HTTPException(400, "Google OAuth isn't configured for this hub yet - an admin sets this up on Settings")
    state = oauth_state.create(user["id"])
    redirect_uri = google_oauth.redirect_uri_for(request, CALLBACK_PATH)
    return {"authorization_url": gmail_oauth.build_authorization_url(state, redirect_uri, client_id)}


@router.get("/auth/callback")
def auth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return oauth_errors.error_page(
            "Gmail connection failed",
            f"Google reported: <code>{error}</code>. If you didn't cancel the consent screen "
            f"yourself, this almost always means the account needs to be added as a test user.",
        )
    if not code or not state:
        return oauth_errors.error_page("Gmail connection failed", "Google didn't send back an authorization code.")
    user_id = oauth_state.pop(state)
    if user_id is None:
        return oauth_errors.error_page(
            "Gmail connection failed",
            "That connection link expired or was already used - go back to Connections and try again.",
        )
    try:
        client_id, client_secret = hub_settings.get_google_oauth_client()
        redirect_uri = google_oauth.redirect_uri_for(request, CALLBACK_PATH)
        tokens = gmail_oauth.exchange_code_for_tokens(code, redirect_uri, client_id, client_secret)
        account_email = gmail_oauth.fetch_user_email(tokens["access_token"])
        gmail_tokens.save_tokens(user_id, tokens, account_email)
    except Exception as exc:  # noqa: BLE001 - want any failure surfaced to the person, not a raw 500
        return oauth_errors.error_page("Gmail connection failed", f"The connection to Google failed: {exc}")
    return RedirectResponse(url="/connections")


@router.delete("/auth")
def disconnect(user: dict = Depends(get_current_user)):
    gmail_tokens.disconnect(user["id"])
    return {"disconnected": True}
