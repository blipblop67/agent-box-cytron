"""
Drive integration: connect via OAuth, then list / read / create / update
files. Each team member connects their own Drive - tokens stored per
user_id, encrypted at rest (see crypto_vault.py). This is what a "Drive" tool
node in the flow builder will call at agent run-time.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from . import drive_client, drive_oauth, drive_tokens, google_oauth, oauth_errors, oauth_state, user_settings
from .auth import get_current_user
from .models import DriveFileContent, DriveFileCreate, DriveFileOut, DriveFileUpdate

router = APIRouter(prefix="/drive", tags=["drive"])

CALLBACK_PATH = "/api/drive/auth/callback"


@router.get("/status")
def status(user: dict = Depends(get_current_user)):
    return drive_tokens.get_connection_status(user["id"]) or {"connected": False}


@router.get("/auth/start")
def auth_start(request: Request, user: dict = Depends(get_current_user)):
    client_id, client_secret = user_settings.resolve_google_credentials(user["id"])
    if not client_id or not client_secret:
        raise HTTPException(500, "Google credentials aren't configured yet - set them up on the Settings or Account page")
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
        client_id, client_secret = user_settings.resolve_google_credentials(user_id)
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


def _require_connected(user_id: str):
    if drive_tokens.get_connection_status(user_id) is None:
        raise HTTPException(400, "Drive is not connected for this user - call /api/drive/auth/start first")


@router.get("/files", response_model=list[DriveFileOut])
def list_files(q: str = "", max_results: int = 20, user: dict = Depends(get_current_user)):
    _require_connected(user["id"])
    return drive_client.list_files(user["id"], search=q, max_results=max_results)


@router.get("/files/{file_id}", response_model=DriveFileOut)
def get_file(file_id: str, user: dict = Depends(get_current_user)):
    _require_connected(user["id"])
    return drive_client.get_file_metadata(user["id"], file_id)


@router.get("/files/{file_id}/content", response_model=DriveFileContent)
def read_file(file_id: str, user: dict = Depends(get_current_user)):
    _require_connected(user["id"])
    return drive_client.read_file_content(user["id"], file_id)


@router.post("/files", response_model=DriveFileOut)
def create_file(body: DriveFileCreate, user: dict = Depends(get_current_user)):
    _require_connected(user["id"])
    return drive_client.create_file(
        user["id"], name=body.name, content=body.content,
        mime_type=body.mime_type, folder_id=body.folder_id,
    )


@router.put("/files/{file_id}/content", response_model=DriveFileOut)
def update_file(file_id: str, body: DriveFileUpdate, user: dict = Depends(get_current_user)):
    _require_connected(user["id"])
    return drive_client.update_file_content(user["id"], file_id, body.content, mime_type=body.mime_type)
