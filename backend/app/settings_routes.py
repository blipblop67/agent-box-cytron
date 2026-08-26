from fastapi import APIRouter, Depends, HTTPException, Request

from . import gmail_routes, drive_routes, calendar_routes, sheets_routes, email_sender, google_oauth, \
    hub_settings, service_account_auth
from .auth import get_current_user
from .models import SettingsOut, SettingsUpdate, TestEmailRequest, TestImpersonationRequest

router = APIRouter(prefix="/settings", tags=["settings"])

IMPERSONATION_TEST_SCOPES = {
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly"],
    "sheets": ["https://www.googleapis.com/auth/spreadsheets.readonly"],
}


def _settings_out(request: Request) -> dict:
    settings = hub_settings.get_settings()
    settings["google_email_redirect_uri"] = google_oauth.redirect_uri_for(request, gmail_routes.CALLBACK_PATH)
    settings["google_drive_redirect_uri"] = google_oauth.redirect_uri_for(request, drive_routes.CALLBACK_PATH)
    settings["google_calendar_redirect_uri"] = google_oauth.redirect_uri_for(request, calendar_routes.CALLBACK_PATH)
    settings["google_sheets_redirect_uri"] = google_oauth.redirect_uri_for(request, sheets_routes.CALLBACK_PATH)
    # all four share the same host, so one check covers all of them
    settings["google_oauth_redirect_warning"] = google_oauth.google_oauth_warning_for(settings["google_email_redirect_uri"])
    return settings


@router.get("", response_model=SettingsOut)
def get_settings(request: Request, user: dict = Depends(get_current_user)):
    return _settings_out(request)


@router.put("", response_model=SettingsOut)
def update_settings(request: Request, body: SettingsUpdate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Only a hub admin can change hub settings")
    try:
        hub_settings.update_settings(**body.model_dump())
    except service_account_auth.ServiceAccountError as exc:
        raise HTTPException(400, str(exc))
    return _settings_out(request)


@router.post("/test-email")
def test_email(body: TestEmailRequest, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Only a hub admin can test the email settings")
    try:
        email_sender.send_email(
            body.to_address, "Agent Hub test email",
            "If you're reading this, outgoing email is configured correctly - password reset "
            "links will actually reach people.",
        )
    except email_sender.EmailError as exc:
        raise HTTPException(400, str(exc))
    return {"sent": True}


@router.post("/test-impersonation")
def test_impersonation(body: TestImpersonationRequest, user: dict = Depends(get_current_user)):
    """Mints a real token acting as body.impersonate and confirms Google
    actually honors it - the concrete way to find out whether domain-wide
    delegation was set up correctly in the Workspace Admin Console, rather
    than discovering it's broken the first time a real flow runs."""
    if user["role"] != "admin":
        raise HTTPException(403, "Only a hub admin can test service account impersonation")
    key_info = hub_settings.get_service_account_key()
    if key_info is None:
        raise HTTPException(400, "No Google service account key is configured yet")
    scopes = IMPERSONATION_TEST_SCOPES.get(body.scope)
    if scopes is None:
        raise HTTPException(400, f"Unknown scope '{body.scope}' - expected one of: {', '.join(IMPERSONATION_TEST_SCOPES)}")
    try:
        service_account_auth.get_access_token_for(key_info, body.impersonate, scopes)
    except service_account_auth.ServiceAccountError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "impersonated": body.impersonate, "scope": body.scope}
