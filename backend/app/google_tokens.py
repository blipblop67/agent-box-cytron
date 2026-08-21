"""
Generic per-user OAuth token lifecycle, parameterized by provider ('gmail',
'drive', ...). Gmail and Drive are separate OAuth grants even against the same
Google account - a user can connect one without the other, and each gets its
own encrypted row in oauth_credentials.

Simplification worth knowing about: get_valid_access_token re-refreshes on
every call rather than caching until near-expiry. One extra HTTP round-trip
per action, in exchange for never tracking expiry timestamps or clock skew -
a reasonable trade for a first version.
"""
import json
from types import ModuleType

from . import crypto_vault, db, user_settings


def save_tokens(user_id: str, provider: str, token_response: dict, account_email: str) -> None:
    refresh_token = token_response.get("refresh_token")
    if not refresh_token:
        # Google only issues a refresh_token on first consent (or when we force
        # prompt=consent, which every *_oauth.py module does) - if it's missing
        # here, something upstream changed and a short-lived access token alone
        # isn't useful long-term.
        raise ValueError(f"Google did not return a refresh token for {provider} - reconnect and try again")
    payload = json.dumps({"refresh_token": refresh_token})
    db.upsert_oauth_credential(user_id, provider, crypto_vault.encrypt(payload), account_email)


def get_valid_access_token(user_id: str, provider: str, oauth_module: ModuleType) -> str:
    row = db.get_oauth_credential(user_id, provider)
    if row is None:
        raise LookupError(f"{provider} is not connected for this user")
    stored = json.loads(crypto_vault.decrypt(row["encrypted_token"]))
    # resolved the same way connecting did: this user's own Google app if
    # they've set one, otherwise the hub-wide default - changing either
    # after connecting means reconnecting, since a refresh token is tied to
    # whichever client requested it
    client_id, client_secret = user_settings.resolve_google_credentials(user_id)
    fresh = oauth_module.refresh_access_token(stored["refresh_token"], client_id, client_secret)
    return fresh["access_token"]


def get_connection_status(user_id: str, provider: str) -> dict | None:
    row = db.get_oauth_credential(user_id, provider)
    if row is None:
        return None
    return {"connected": True, "account_email": row["account_email"], "connected_at": row["created_at"]}


def disconnect(user_id: str, provider: str) -> None:
    db.delete_oauth_credential(user_id, provider)
