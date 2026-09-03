"""
Direct Drive action endpoints - list / read / create / update files - for
manual use, testing, and the Drive node's file picker in the flow editor,
plus the OAuth connection lifecycle for Path B (personal "Connect" flow -
see google_oauth.py's docstring for why this exists alongside the service
account model, not instead of it). A flow's Drive node goes through
flow_engine.py directly rather than either of these; this router is a
plain API surface over drive_client.py, which does the actual work.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from . import drive_client, drive_oauth, drive_tokens, google_oauth, hub_settings, oauth_errors, oauth_state
from .auth import get_current_user
from .models import DriveFileContent, DriveFileCreate, DriveFileOut, DriveFileUpdate


router = APIRouter(prefix="/drive", tags=["drive"])

CALLBACK_PATH = "/api/drive/auth/callback"


@router.get("/files", response_model=list[DriveFileOut])
def list_files(q: str = "", max_results: int = 20, impersonate: str | None = None,
                user: dict = Depends(get_current_user)):
    try:
        return drive_client.list_files(search=q, max_results=max_results, impersonate=impersonate)
    except (ValueError, drive_client.DriveError) as exc:
        raise HTTPException(400, str(exc))


@router.get("/files/{file_id}", response_model=DriveFileOut)
def get_file(file_id: str, impersonate: str | None = None, user: dict = Depends(get_current_user)):
    try:
        return drive_client.get_file_metadata(file_id, impersonate=impersonate)
    except (ValueError, drive_client.DriveError) as exc:
        raise HTTPException(400, str(exc))


@router.get("/files/{file_id}/content", response_model=DriveFileContent)
def read_file(file_id: str, impersonate: str | None = None, user: dict = Depends(get_current_user)):
    try:
        return drive_client.read_file_content(file_id, impersonate=impersonate)
    except (ValueError, drive_client.DriveError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/files", response_model=DriveFileOut)
def create_file(body: DriveFileCreate, user: dict = Depends(get_current_user)):
    try:
        return drive_client.create_file(
            name=body.name, content=body.content, mime_type=body.mime_type,
            folder_id=body.folder_id, impersonate=body.impersonate,
        )
    except (ValueError, drive_client.DriveError) as exc:
        raise HTTPException(400, str(exc))


@router.put("/files/{file_id}/content", response_model=DriveFileOut)
def update_file(file_id: str, body: DriveFileUpdate, user: dict = Depends(get_current_user)):
    try:
        return drive_client.update_file_content(file_id, body.content, mime_type=body.mime_type, impersonate=body.impersonate)
    except (ValueError, drive_client.DriveError) as exc:
        raise HTTPException(400, str(exc))


# ---- OAuth connection lifecycle (Path B - personal "Connect" flow) --------

@router.get("/status")
def status(user: dict = Depends(get_current_user)):
    return drive_tokens.get_connection_status(user["id"]) or {"connected": False}


@router.get("/auth/start")
def auth_start(request: Request, user: dict = Depends(get_current_user)):
    client_id, client_secret = hub_settings.get_google_oauth_client()
    if not client_id or not client_secret:
        raise HTTPException(400, "Google OAuth isn't configured for this hub yet - an admin sets this up on Settings")
    state = oauth_state.create(user["id"])
    redirect_uri = google_oauth.redirect_uri_for(request, CALLBACK_PATH)
    return {"authorization_url": drive_oauth.build_authorization_url(state, redirect_uri, client_id)}


@router.get("/auth/callback")
def auth_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error:
        return oauth_errors.error_page(
            "Drive connection failed",
            f"Google reported: <code>{error}</code>. If you didn't cancel the consent screen "
            f"yourself, this almost always means the account needs to be added as a test user.",
        )
    if not code or not state:
        return oauth_errors.error_page("Drive connection failed", "Google didn't send back an authorization code.")
    user_id = oauth_state.pop(state)
    if user_id is None:
        return oauth_errors.error_page(
            "Drive connection failed",
            "That connection link expired or was already used - go back to Connections and try again.",
        )
    try:
        client_id, client_secret = hub_settings.get_google_oauth_client()
        redirect_uri = google_oauth.redirect_uri_for(request, CALLBACK_PATH)
        tokens = drive_oauth.exchange_code_for_tokens(code, redirect_uri, client_id, client_secret)
        account_email = drive_oauth.fetch_user_email(tokens["access_token"])
        drive_tokens.save_tokens(user_id, tokens, account_email)
    except Exception as exc:  # noqa: BLE001 - want any failure surfaced to the person, not a raw 500
        return oauth_errors.error_page("Drive connection failed", f"The connection to Google failed: {exc}")
    return RedirectResponse(url="/connections")


@router.delete("/auth")
def disconnect(user: dict = Depends(get_current_user)):
    drive_tokens.disconnect(user["id"])
    return {"disconnected": True}
