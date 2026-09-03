"""
Hub-wide settings, admin-configurable from the Settings page: the LLM
provider, a Google service account key (the only way this hub talks to
Google - see service_account_auth.py), a web search key, a YouTube key,
outgoing SMTP settings, and an optional DuckDNS domain for networks where
`.local` resolution doesn't work.

There's no OAuth client ID/secret or redirect URI concept here - removing
per-user OAuth for Google entirely also removed that whole class of
problem, since a service account never involves a browser redirect at
all. DuckDNS below is unrelated to Google - it's purely about network
reachability, opt-in, for anyone whose network blocks mDNS.
"""
import time

from fastapi import APIRouter, Depends, HTTPException

from . import db, dynamic_dns, email_sender, hub_settings, service_account_auth
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
        raise HTTPException(400, "DuckDNS isn't configured yet - save a subdomain and token first")
    subdomain, token = creds
    try:
        result = dynamic_dns.update(subdomain, token)
    except dynamic_dns.DuckDnsError as exc:
        db.set_setting("duckdns_last_error", str(exc))
        raise HTTPException(400, str(exc))
    db.set_setting("duckdns_last_updated_ip", result["ip"])
    db.set_setting("duckdns_last_updated_at", str(time.time()))
    db.set_setting("duckdns_last_error", "")
    return {"ok": True, "domain": result["domain"], "ip": result["ip"]}
