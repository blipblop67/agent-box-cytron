"""
Google Sheets integration: connect via OAuth, then create a spreadsheet,
read it, or upsert a row (find by key in column A, update in place, or
append if it's new). Each team member connects their own account - tokens
stored per user_id, encrypted at rest. This is what a "Sheets" tool node
in the flow builder calls at agent run-time.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from . import google_oauth, oauth_errors, oauth_state, sheets_client, sheets_oauth, sheets_tokens, user_settings
from .auth import get_current_user

router = APIRouter(prefix="/sheets", tags=["sheets"])

CALLBACK_PATH = "/api/sheets/auth/callback"


@router.get("/status")
def status(user: dict = Depends(get_current_user)):
    return sheets_tokens.get_connection_status(user["id"]) or {"connected": False}


@router.get("/auth/start")
def auth_start(request: Request, user: dict = Depends(get_current_user)):
    client_id, client_secret = user_settings.resolve_google_credentials(user["id"])
    if not client_id or not client_secret:
        raise HTTPException(500, "Google credentials aren't configured yet - set them up on the Settings or Account page")
    state = oauth_state.create(user["id"])
    redirect_uri = google_oauth.redirect_uri_for(request, CALLBACK_PATH)
    return {"authorization_url": sheets_oauth.build_authorization_url(state, redirect_uri, client_id)}


@router.get("/auth/callback")
def auth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return oauth_errors.error_page(
            "Sheets connection failed",
            f"Google reported: <code>{error}</code>. If you didn't cancel the consent screen "
            f"yourself, this almost always means the account needs to be added as a test user.",
        )
    if not code or not state:
        return oauth_errors.error_page("Sheets connection failed", "Google didn't send back an authorization code.")
    user_id = oauth_state.pop(state)
    if user_id is None:
        return oauth_errors.error_page(
            "Sheets connection failed",
            "That connection link expired or was already used - go back to Connections and try again.",
        )
    try:
        client_id, client_secret = user_settings.resolve_google_credentials(user_id)
        redirect_uri = google_oauth.redirect_uri_for(request, CALLBACK_PATH)
        tokens = sheets_oauth.exchange_code_for_tokens(code, redirect_uri, client_id, client_secret)
        account_email = sheets_oauth.fetch_user_email(tokens["access_token"])
        sheets_tokens.save_tokens(user_id, tokens, account_email)
    except Exception as exc:  # noqa: BLE001 - want any failure surfaced to the person, not a raw 500
        return oauth_errors.error_page("Sheets connection failed", f"The connection to Google failed: {exc}")
    return RedirectResponse(url="/connections")


@router.delete("/auth")
def disconnect(user: dict = Depends(get_current_user)):
    sheets_tokens.disconnect(user["id"])
    return {"disconnected": True}


def _require_connected(user_id: str):
    if sheets_tokens.get_connection_status(user_id) is None:
        raise HTTPException(400, "Sheets is not connected for this user - call /api/sheets/auth/start first")


class CreateSpreadsheetRequest(BaseModel):
    title: str
    headers: list[str] | None = None
    sheet_name: str = "Sheet1"


@router.post("/spreadsheets")
def create_spreadsheet(body: CreateSpreadsheetRequest, user: dict = Depends(get_current_user)):
    _require_connected(user["id"])
    try:
        return sheets_client.create_spreadsheet(user["id"], body.title, body.headers, body.sheet_name)
    except sheets_client.SheetsError as exc:
        raise HTTPException(400, str(exc))


@router.get("/spreadsheets/{spreadsheet_id}/rows")
def read_rows(spreadsheet_id: str, sheet_name: str = "Sheet1", user: dict = Depends(get_current_user)):
    _require_connected(user["id"])
    try:
        return {"rows": sheets_client.read_rows(user["id"], spreadsheet_id, sheet_name)}
    except sheets_client.SheetsError as exc:
        raise HTTPException(400, str(exc))


class UpsertRowRequest(BaseModel):
    sheet_name: str = "Sheet1"
    values: list[str]


@router.post("/spreadsheets/{spreadsheet_id}/upsert-row")
def upsert_row(spreadsheet_id: str, body: UpsertRowRequest, user: dict = Depends(get_current_user)):
    _require_connected(user["id"])
    try:
        return sheets_client.upsert_row(user["id"], spreadsheet_id, body.sheet_name, body.values)
    except sheets_client.SheetsError as exc:
        raise HTTPException(400, str(exc))
