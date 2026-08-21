"""
Calendar's slice of the generic token lifecycle - just binds the provider
name and which oauth module knows how to refresh. See google_tokens.py for
the actual storage/refresh logic (shared with Gmail and Drive).
"""
from . import calendar_oauth, google_tokens

PROVIDER = "calendar"


def save_tokens(user_id: str, token_response: dict, account_email: str) -> None:
    google_tokens.save_tokens(user_id, PROVIDER, token_response, account_email)


def get_valid_access_token(user_id: str) -> str:
    return google_tokens.get_valid_access_token(user_id, PROVIDER, calendar_oauth)


def get_connection_status(user_id: str) -> dict | None:
    return google_tokens.get_connection_status(user_id, PROVIDER)


def disconnect(user_id: str) -> None:
    google_tokens.disconnect(user_id, PROVIDER)
