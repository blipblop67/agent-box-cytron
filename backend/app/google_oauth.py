"""
Generic Google OAuth2 authorization-code flow via plain httpx REST calls -
shared by Gmail, Drive, Calendar, and Sheets. Each product module supplies
its own scope list and calls these directly.

Deliberately not pulling in google-auth-oauthlib / google-api-python-client,
same reasoning as everywhere else in this codebase: three REST calls don't
need a whole SDK.

This is the "Path B" option alongside the service account model
(service_account_auth.py), not a replacement for it - domain-wide
delegation and the Apps Script bridge both still exist and work today.
This exists for whoever wants the familiar "click Connect, sign in with
Google" experience instead, at the cost each customer accepts
deliberately: their own Google Cloud project, one OAuth client, one set
of credentials pasted into Settings by their own admin. Every OAuth
client has exactly one owner now - there's no "which customer does this
belong to" ambiguity the way a single shared client across many
deployments would have, since that's structurally impossible with
Google's OAuth (see the design notes in backend/README.md for why).

Client ID/secret are hub-wide (see hub_settings.py) - one Google Cloud
project per customer, matching how the service account key already
works. Nothing in this file caches credentials, so a change takes effect
on the very next call.
"""
import re
import urllib.parse

import httpx

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"


def build_authorization_url(scopes: list[str], state: str, redirect_uri: str, client_id: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",  # ask for a refresh token, not just a short-lived access token
        "prompt": "consent",       # force a fresh refresh token even if the user connected before
        "state": state,
    }
    return f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(code: str, redirect_uri: str, client_id: str, client_secret: str) -> dict:
    resp = httpx.post(
        TOKEN_ENDPOINT,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()  # {access_token, refresh_token, expires_in, ...}


def refresh_access_token(refresh_token: str, client_id: str, client_secret: str) -> dict:
    resp = httpx.post(
        TOKEN_ENDPOINT,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()  # {access_token, expires_in, ...} - Google usually omits refresh_token here


def fetch_user_email(access_token: str) -> str:
    resp = httpx.get(USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {access_token}"}, timeout=30)
    resp.raise_for_status()
    return resp.json()["email"]


def redirect_uri_for(request, callback_path: str) -> str:
    """Derives the redirect_uri from whatever host/port the browser is
    actually using to reach the hub right now, rather than a fixed setting -
    nothing to keep in sync if the hub is reached by more than one hostname
    (the unique agenthub-xxxxxxxx.local name, a DuckDNS domain, a raw IP),
    as long as each one you actually use is also registered as a redirect
    URI on this hub's own OAuth client in Google Cloud Console."""
    return f"{str(request.base_url).rstrip('/')}{callback_path}"


_IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def google_oauth_warning_for(redirect_uri: str) -> str | None:
    """Google's own client-side validation rejects a redirect URI whose
    host isn't either localhost/127.0.0.1 (its one loopback exception) or
    a domain with a real public suffix - which rules out exactly the two
    ways this hub is normally reached: a `.local` mDNS name (not a real,
    ownable TLD) and a raw LAN IP (no TLD at all). Both fail with the
    same confusing Guava-powered error in Google Cloud Console:
    "must use a domain that is a valid top private domain." This isn't a
    bug in the URI this hub computes - it's a hard limit of what Google's
    OAuth "Web application" client type will ever accept - so the fix is
    catching it here and telling someone before they hit that error in
    Google Cloud Console with no context. The DuckDNS card elsewhere in
    Settings is the direct fix, if this warning is showing."""
    host = urllib.parse.urlparse(redirect_uri).hostname or ""
    if host in ("localhost", "127.0.0.1"):
        return None
    if host.endswith(".local") or _IPV4_RE.match(host):
        return (
            f"This hub is currently reachable at a `.local` name or raw IP ({host}), which Google's "
            f"OAuth setup will reject as a redirect URI - it needs a real domain (even a free one) or "
            f"localhost specifically. Set up the free DuckDNS option elsewhere on this Settings page, "
            f"then use that address instead when creating the OAuth client in Google Cloud Console."
        )
    return None
