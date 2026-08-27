"""
Google service account authentication - the only way this hub talks to
Google now, for every service (Gmail, Drive, Calendar, Sheets). This
replaces the old per-user OAuth consent flow entirely, matching how
Langflow's own Google integrations work: paste a service account's JSON
key once, and every node authenticates through it - no browser, no
consent screen, no redirect URI, and so no way for Google's redirect-URI
rules (no `.local` names, no raw IPs) to ever come up, because there's no
redirect involved at any point.

Two ways a node can use this key:
- **Impersonating a specific person** (the "Impersonate" field on a
  node): a Workspace super admin has to authorize this service account,
  once, in the Admin Console (not Cloud Console) to act as that person
  for specific scopes. Needed to read/write an *existing* person's
  mailbox or Drive - there's no way around a human with Workspace admin
  rights granting this, no matter how this hub is built, since it's a
  Google-side authorization, not something client code can shortcut.
- **Acting as the service account itself** (Impersonate left blank): no
  admin authorization needed at all - Drive/Sheets/Calendar files the
  service account creates land in its own space, and anything shared
  with its email address (exactly like sharing with a colleague) becomes
  accessible to it. Gmail specifically has no meaningful "own inbox" for
  a plain service account, so leaving Impersonate blank on an Email node
  will fail with a clear Google error unless a Workspace admin has
  specifically provisioned a mailbox for it - an unusual, deliberate
  setup, not the common case.

Hand-rolled RS256 JWT signing (via `cryptography`, already a dependency)
and a plain httpx POST for the token exchange, rather than pulling in
`google-auth` - consistent with how every *_client.py module in this
codebase already does plain REST instead of the official SDK.

The trust model is worth being explicit about: whoever can set this
credential can make it act as *any* user the Admin Console has
authorized it for - a materially bigger blast radius than the old
personal-OAuth model, where a connection only ever granted access to the
one account that clicked "Allow." Hub-wide, admin-only, by design.
"""
import base64
import json
import time

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

TOKEN_URI = "https://oauth2.googleapis.com/token"


class ServiceAccountError(Exception):
    pass


def parse_key(raw_json: str) -> dict:
    """Validates a pasted/uploaded service account JSON key has the fields
    this module actually needs, before anything tries to use it."""
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ServiceAccountError("That doesn't look like valid JSON") from exc
    if data.get("type") != "service_account":
        raise ServiceAccountError(
            "That JSON key isn't a service account key (expected \"type\": \"service_account\") - "
            "download it from Google Cloud Console under IAM & Admin -> Service Accounts -> Keys"
        )
    missing = [f for f in ("client_email", "private_key", "private_key_id") if not data.get(f)]
    if missing:
        raise ServiceAccountError(f"The key JSON is missing required field(s): {', '.join(missing)}")
    return data


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign(private_key_pem: str, message: bytes) -> bytes:
    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    return private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())


def build_signed_jwt(key_info: dict, scopes: list[str], subject: str | None = None) -> str:
    """`subject` set means domain-wide delegation - "issue this as if
    <subject> had granted it," which only succeeds if a Workspace super
    admin has explicitly authorized this exact service account for these
    exact scopes. `subject` left as None means the service account is
    authenticating as itself - no admin authorization needed, but it only
    has access to what's been directly shared with its own email address
    (Drive/Sheets/Calendar) or what it created itself."""
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": key_info["client_email"],
        "scope": " ".join(scopes),
        "aud": TOKEN_URI,
        "iat": now,
        "exp": now + 3600,
    }
    if subject:
        claims["sub"] = subject
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"
    signature = _sign(key_info["private_key"], signing_input.encode())
    return f"{signing_input}.{_b64url(signature)}"


def get_access_token(key_info: dict, scopes: list[str], subject: str | None = None) -> str:
    """The actual token a Gmail/Drive/Calendar/Sheets client can use -
    acting as `subject` if given (domain-wide delegation), or as the
    service account itself otherwise."""
    assertion = build_signed_jwt(key_info, scopes, subject)
    try:
        resp = httpx.post(
            TOKEN_URI,
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise ServiceAccountError(f"Couldn't reach Google to mint a token: {exc}") from exc

    if resp.status_code == 200:
        return resp.json()["access_token"]

    try:
        error_body = resp.json()
    except ValueError:
        error_body = {}
    error_code = error_body.get("error", "")
    detail = error_body.get("error_description") or error_code or resp.text
    if subject and error_code in ("unauthorized_client", "access_denied"):
        raise ServiceAccountError(
            f"Google refused to let this service account act as '{subject}' ({detail}). This almost "
            f"always means domain-wide delegation for this exact service account and these exact "
            f"scopes hasn't been authorized in the Workspace Admin Console yet - that's a separate "
            f"step from creating the key in Cloud Console, and needs a Workspace super admin."
        )
    if not subject and error_code in ("unauthorized_client", "access_denied", "invalid_grant"):
        raise ServiceAccountError(
            f"Google rejected this request acting as the service account itself ({detail}). A plain "
            f"service account has no inbox of its own for Gmail - if this is an Email node, set "
            f"'Impersonate' to a real Workspace address instead. For Drive/Sheets/Calendar, make sure "
            f"whatever you're trying to reach has actually been shared with this service account's "
            f"own email address."
        )
    raise ServiceAccountError(f"Google rejected the token request: {detail}")


# Backwards-compatible alias for the (subject-required) name used before this
# module also handled the no-impersonation case - kept for anything that
# still calls it positionally with a required subject.
def get_access_token_for(key_info: dict, subject: str, scopes: list[str]) -> str:
    return get_access_token(key_info, scopes, subject)
