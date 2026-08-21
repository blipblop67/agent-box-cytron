"""
Gmail's slice of the generic Google OAuth flow - just the scopes. Client
credentials and the redirect URI are resolved per-request/per-user by the
caller (gmail_routes.py) and passed straight through.
"""
from . import google_oauth

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",  # read + reply + basic label management
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def build_authorization_url(state: str, redirect_uri: str, client_id: str) -> str:
    return google_oauth.build_authorization_url(SCOPES, state, redirect_uri, client_id)


def exchange_code_for_tokens(code: str, redirect_uri: str, client_id: str, client_secret: str) -> dict:
    return google_oauth.exchange_code_for_tokens(code, redirect_uri, client_id, client_secret)


def refresh_access_token(refresh_token: str, client_id: str, client_secret: str) -> dict:
    return google_oauth.refresh_access_token(refresh_token, client_id, client_secret)


def fetch_user_email(access_token: str) -> str:
    return google_oauth.fetch_user_email(access_token)
