"""
Drive's slice of the generic Google OAuth flow. Client credentials and the
redirect URI are resolved per-request/per-user by the caller
(drive_routes.py) and passed straight through.

Scope choice matters here: `drive.readonly` lets an agent read anything in
the user's Drive (needed for "summarize this doc" style tasks), but write
access is deliberately narrower - `drive.file` only lets the hub create new
files and edit files *it* created, not silently overwrite a pre-existing
document it never touched. If a team later needs to edit arbitrary existing
files, broaden to the full `drive` scope - just know that's a bigger blast
radius if a token is ever compromised.
"""
from . import google_oauth

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
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
