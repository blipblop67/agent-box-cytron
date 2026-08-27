"""
Hub-wide settings, admin-configurable from the Settings page: the LLM
provider, a Google service account key (the only way this hub talks to
Google - see service_account_auth.py), a web search key, a YouTube key,
and outgoing SMTP settings.

There's no OAuth client ID/secret or redirect URI concept here anymore -
removing per-user OAuth for Google entirely also removed the whole class
of problem that came with it (Google's redirect URI rejecting `.local`
names and raw IPs, needing a real domain, DuckDNS, Tailscale, etc.) since
a service account never involves a browser redirect at all.
"""
from fastapi import APIRouter, Depends, HTTPException

from . import email_sender, hub_settings, service_account_auth
from .auth import get_current_user
from .models import SettingsOut, SettingsUpdate, TestEmailRequest, TestImpersonationRequest

router = APIRouter(prefix="/settings", tags=["settings"])

IMPERSONATION_TEST_SCOPES = {
    "gmail": ["https://www.googleapis.com/auth/gmail.readonly"],
    "sheets": ["https://www.googleapis.com/auth/spreadsheets.readonly"],
}


@router.get("", response_model=SettingsOut)
def get_settings(user: dict = Depends(get_current_user)):
    return hub_settings.get_settings()


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Only a hub admin can change hub settings")
    try:
        hub_settings.update_settings(**body.model_dump())
    except service_account_auth.ServiceAccountError as exc:
        raise HTTPException(400, str(exc))
    return hub_settings.get_settings()


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
    """Mints a real token acting as body.impersonate (or as the service
    account itself, if left blank) and confirms Google actually honors
    it - the concrete way to find out whether domain-wide delegation was
    set up correctly in the Workspace Admin Console, rather than
    discovering it's broken the first time a real flow runs."""
    if user["role"] != "admin":
        raise HTTPException(403, "Only a hub admin can test service account access")
    key_info = hub_settings.get_service_account_key()
    if key_info is None:
        raise HTTPException(400, "No Google service account key is configured yet")
    scopes = IMPERSONATION_TEST_SCOPES.get(body.scope)
    if scopes is None:
        raise HTTPException(400, f"Unknown scope '{body.scope}' - expected one of: {', '.join(IMPERSONATION_TEST_SCOPES)}")
    try:
        service_account_auth.get_access_token(key_info, scopes, body.impersonate or None)
    except service_account_auth.ServiceAccountError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "impersonated": body.impersonate, "scope": body.scope}
