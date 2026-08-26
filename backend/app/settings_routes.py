import time
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Request

from . import db, gmail_routes, drive_routes, calendar_routes, sheets_routes, dynamic_dns, email_sender, \
    google_oauth, hub_settings, service_account_auth
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
    warning = google_oauth.google_oauth_warning_for(settings["google_email_redirect_uri"])
    if warning and settings["duckdns_configured"]:
        # already have a real fix in hand - say so directly instead of the generic "get a domain" advice
        port = urllib.parse.urlparse(settings["google_email_redirect_uri"]).port
        suggested = f"http://{settings['duckdns_subdomain']}.duckdns.org" + (f":{port}" if port else "")
        warning = (
            f"You're reachable at {suggested} now (DuckDNS is already configured below) - use that "
            f"address instead of this one for Google sign-in, and Google will accept it."
        )
    settings["google_oauth_redirect_warning"] = warning
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


@router.post("/duckdns/update-now")
def duckdns_update_now(user: dict = Depends(get_current_user)):
    """Triggers an immediate update rather than waiting for the next
    background refresh (scheduler.py, every 5 minutes) - lets someone
    confirm it actually works right after saving credentials, instead of
    wondering whether it's configured correctly for the next few minutes."""
    if user["role"] != "admin":
        raise HTTPException(403, "Only a hub admin can update DuckDNS")
    creds = hub_settings.get_duckdns_credentials()
    if creds is None:
        raise HTTPException(400, "DuckDNS isn't configured yet - add a subdomain and token first")
    subdomain, token = creds
    try:
        result = dynamic_dns.update(subdomain, token)
    except dynamic_dns.DuckDnsError as exc:
        raise HTTPException(400, str(exc))
    db.set_setting("duckdns_last_updated_ip", result["ip"])
    db.set_setting("duckdns_last_updated_at", str(time.time()))
    db.set_setting("duckdns_last_error", "")
    return result
