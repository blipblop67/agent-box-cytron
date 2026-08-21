"""
Generic Google OAuth2 authorization-code flow via plain httpx REST calls -
shared by every Google product we integrate (Gmail today, Drive next).
Each product module supplies its own scope list and calls these directly.

Deliberately not pulling in google-auth-oauthlib / google-api-python-client,
which drag in protobuf and a lot of weight for what is, underneath, three
REST calls. Setup happens over the LAN in a browser, so Google can redirect
straight back to the hub's own callback URL - no public domain or cloud
relay needed.

Client ID/secret are passed in explicitly by the caller (see
gmail_routes.py / drive_routes.py), which resolves them per-user via
user_settings.resolve_google_credentials - someone's own Google app if
they've set one, otherwise the hub-wide default. Nothing in this file
caches credentials, so a change takes effect on the very next call.
"""
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
    (agenthub.local vs a raw IP), as long as each one you actually use is
    also registered as a redirect URI in Google Cloud Console."""
    return f"{str(request.base_url).rstrip('/')}{callback_path}"
