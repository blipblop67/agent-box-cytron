"""
Google service account authentication, for Workspace domain-wide
delegation - a completely different auth model from google_oauth.py's
per-user consent flow, and the reason it exists separately rather than
folded into it.

Per-user OAuth (google_oauth.py) needs a browser redirect back to this
hub, which is why it hits Google's redirect-URI restrictions (no `.local`
names, no raw IPs, no private IPs at all even via a real domain - see
google_oauth.py's warning helper). A service account has no redirect at
all: a Workspace super admin authorizes it once, in the Admin Console
(not Cloud Console), to impersonate any user in the domain for specific
scopes. From then on, this hub mints a short-lived access token per
request by signing a JWT with the service account's own private key -
no browser involved, no redirect URI, nothing for Google to reject on
that front.

This is deliberately hand-rolled (raw JWT construction + RSA signing via
`cryptography`, a plain httpx POST for the token exchange) rather than
pulling in `google-auth`, matching how gmail_client.py/drive_client.py/
etc. already do plain REST instead of the official SDKs - the same
reasoning applies here: a handful of REST calls don't need a whole
library, and this hub touches so few Google endpoints that the SDK's
abstraction doesn't pay for its own weight.

The trust model is worth being explicit about: whoever can set this
credential can make it act as *any* user in the Workspace domain, for
whatever scopes were granted in the Admin Console - a materially bigger
blast radius than a personal OAuth connection, which only ever grants
access to the one account that clicked "Allow." Hub-wide, admin-only,
by design.
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


def build_signed_jwt(key_info: dict, scopes: list[str], subject: str) -> str:
    """The `sub` (subject) claim is what makes this domain-wide delegation
    rather than the service account acting as itself: it tells Google
    "issue this token as if <subject> had granted it," which only
    succeeds if a Workspace super admin has explicitly authorized this
    exact service account for these exact scopes in the Admin Console."""
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": key_info["client_email"],
        "scope": " ".join(scopes),
        "aud": TOKEN_URI,
        "iat": now,
        "exp": now + 3600,
        "sub": subject,
    }
    signing_input = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"
    signature = _sign(key_info["private_key"], signing_input.encode())
    return f"{signing_input}.{_b64url(signature)}"


def get_access_token_for(key_info: dict, subject: str, scopes: list[str]) -> str:
    """The actual token a Gmail/Drive/Calendar/Sheets client can use,
    acting as `subject` (e.g. hairil@cytron.io) rather than the service
    account itself."""
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
    if error_code in ("unauthorized_client", "access_denied"):
        raise ServiceAccountError(
            f"Google refused to let this service account act as '{subject}' ({detail}). This almost "
            f"always means domain-wide delegation for this exact service account and these exact "
            f"scopes hasn't been authorized in the Workspace Admin Console yet - that's a separate "
            f"step from creating the key in Cloud Console, and needs a Workspace super admin."
        )
    raise ServiceAccountError(f"Google rejected the token request: {detail}")
