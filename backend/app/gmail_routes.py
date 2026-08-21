"""
Gmail integration: connect via OAuth, then send / list / read / reply.
Each team member connects their own Gmail account - tokens are stored per
user_id, encrypted at rest (see crypto_vault.py). This is what an "Email" tool
node in the flow builder will call at agent run-time.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from . import gmail_client, gmail_oauth, gmail_tokens, google_oauth, oauth_errors, oauth_state, user_settings
from .auth import get_current_user

router = APIRouter(prefix="/email", tags=["email"])

CALLBACK_PATH = "/api/email/auth/callback"


@router.get("/status")
def status(user: dict = Depends(get_current_user)):
    return gmail_tokens.get_connection_status(user["id"]) or {"connected": False}


@router.get("/auth/start")
def auth_start(request: Request, user: dict = Depends(get_current_user)):
    client_id, client_secret = user_settings.resolve_google_credentials(user["id"])
    if not client_id or not client_secret:
        raise HTTPException(500, "Google credentials aren't configured yet - set them up on the Settings or Account page")
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
        client_id, client_secret = user_settings.resolve_google_credentials(user_id)
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


def _require_connected(user_id: str):
    if gmail_tokens.get_connection_status(user_id) is None:
        raise HTTPException(400, "Gmail is not connected for this user - call /api/email/auth/start first")


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str


@router.post("/send")
def send(body: SendEmailRequest, user: dict = Depends(get_current_user)):
    _require_connected(user["id"])
    return gmail_client.send_email(user["id"], to=body.to, subject=body.subject, body=body.body)


@router.get("/messages")
def list_messages(q: str = "", max_results: int = 10, user: dict = Depends(get_current_user)):
    _require_connected(user["id"])
    return gmail_client.list_messages(user["id"], query=q, max_results=max_results)


@router.get("/messages/{message_id}")
def get_message(message_id: str, user: dict = Depends(get_current_user)):
    _require_connected(user["id"])
    return gmail_client.get_message(user["id"], message_id)


class ReplyRequest(BaseModel):
    body: str


@router.post("/messages/{message_id}/reply")
def reply(message_id: str, body: ReplyRequest, user: dict = Depends(get_current_user)):
    _require_connected(user["id"])
    return gmail_client.reply_to_message(user["id"], message_id, body.body)
