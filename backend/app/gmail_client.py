"""
Thin wrapper around the Gmail REST API v1 - send, list, read, and reply.
Raw REST + stdlib `email.mime` rather than the official Google client
library, for the same "keep it small and readable" reason as
service_account_auth.py.

Authenticates entirely through the hub-wide Google service account (see
service_account_auth.py) - there's no per-user OAuth connection anymore.
`impersonate` (a Workspace email) is required in practice for Gmail
specifically: a plain service account has no inbox of its own, so
leaving it blank will fail unless a Workspace admin has specifically
provisioned a mailbox for the service account itself, which is unusual -
_handle_error below turns that specific failure into a clear, actionable
message rather than a raw HTTP exception.
"""
import base64
from email.mime.text import MIMEText
from email.utils import parseaddr

import httpx

from . import hub_settings, service_account_auth

API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",  # read + reply + basic label management
]


class GmailError(Exception):
    pass


def _headers(impersonate: str | None = None, access_token: str | None = None) -> dict:
    """access_token, when given, is a resolved per-user OAuth token (Path B -
    see google_tokens.py) and is used directly, bypassing the service
    account entirely - the flow engine resolves this before calling in,
    based on the node's own auth_mode setting. Leaving it unset is the
    default, unchanged path: the hub-wide service account, optionally
    impersonating someone via domain-wide delegation."""
    if access_token:
        return {"Authorization": f"Bearer {access_token}"}
    key_info = hub_settings.get_service_account_key()
    if key_info is None:
        raise GmailError("Gmail isn't configured yet - add a Google service account key on the Settings page")
    try:
        token = service_account_auth.get_access_token(key_info, SCOPES, impersonate)
    except service_account_auth.ServiceAccountError as exc:
        raise GmailError(str(exc)) from exc
    return {"Authorization": f"Bearer {token}"}


def _handle_error(resp: httpx.Response, impersonate: str | None, context: str) -> None:
    if resp.status_code < 400:
        return
    try:
        detail = resp.json().get("error", {}).get("message", resp.text)
    except ValueError:
        detail = resp.text
    if not impersonate:
        raise GmailError(
            f"Gmail rejected this ({context}: \"{detail}\"). A plain service account has no real "
            f"inbox of its own - set this node's 'Impersonate' field to a real Workspace address "
            f"instead (needs domain-wide delegation authorized for that address's scope first)."
        )
    raise GmailError(f"Gmail rejected this ({context} as '{impersonate}'): {detail}")


def _b64url_encode(raw_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(raw_bytes).decode()


def _b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode(errors="ignore")


def send_email(to: str, subject: str, body: str, *,
                thread_id: str | None = None, in_reply_to: str | None = None,
                references: str | None = None, impersonate: str | None = None,
                access_token: str | None = None) -> dict:
    msg = MIMEText(body)
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    payload = {"raw": _b64url_encode(msg.as_bytes())}
    if thread_id:
        payload["threadId"] = thread_id

    resp = httpx.post(f"{API_BASE}/messages/send", headers=_headers(impersonate, access_token), json=payload, timeout=30)
    _handle_error(resp, impersonate, "sending an email")
    return resp.json()


def list_messages(query: str = "", max_results: int = 10, *, impersonate: str | None = None,
                   access_token: str | None = None) -> list[dict]:
    """Cheap listing: headers + snippet only (format=metadata), not the full body -
    good for scanning an inbox without pulling every message's full content."""
    params = {"maxResults": max_results}
    if query:
        params["q"] = query
    resp = httpx.get(f"{API_BASE}/messages", headers=_headers(impersonate, access_token), params=params, timeout=30)
    _handle_error(resp, impersonate, "listing messages")
    ids = [m["id"] for m in resp.json().get("messages", [])]
    return [_get_message_metadata(mid, impersonate, access_token) for mid in ids]


def _get_message_metadata(message_id: str, impersonate: str | None = None, access_token: str | None = None) -> dict:
    resp = httpx.get(
        f"{API_BASE}/messages/{message_id}",
        headers=_headers(impersonate, access_token),
        params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date", "Message-ID"]},
        timeout=30,
    )
    _handle_error(resp, impersonate, "reading a message")
    return _parse_message(resp.json(), include_body=False)


def get_message(message_id: str, *, impersonate: str | None = None, access_token: str | None = None) -> dict:
    """Full read: headers plus the plain-text body, for when an agent actually
    needs to read what an email says, not just its subject line."""
    resp = httpx.get(
        f"{API_BASE}/messages/{message_id}",
        headers=_headers(impersonate, access_token),
        params={"format": "full"},
        timeout=30,
    )
    _handle_error(resp, impersonate, "reading a message")
    return _parse_message(resp.json(), include_body=True)


def reply_to_message(message_id: str, body: str, *, impersonate: str | None = None,
                      access_token: str | None = None) -> dict:
    original = get_message(message_id, impersonate=impersonate, access_token=access_token)
    to_address = parseaddr(original["from"])[1]
    subject = original["subject"] or ""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    return send_email(
        to=to_address, subject=subject, body=body,
        thread_id=original["thread_id"],
        in_reply_to=original["message_id_header"],
        references=original["message_id_header"],
        impersonate=impersonate, access_token=access_token,
    )


def _parse_message(data: dict, include_body: bool) -> dict:
    headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
    result = {
        "id": data["id"],
        "thread_id": data["threadId"],
        "snippet": data.get("snippet", ""),
        "from": headers.get("From"),
        "to": headers.get("To"),
        "subject": headers.get("Subject"),
        "date": headers.get("Date"),
        "message_id_header": headers.get("Message-ID"),
    }
    if include_body:
        result["body"] = _extract_plain_text(data.get("payload", {}))
    return result


def _extract_plain_text(payload: dict) -> str:
    """Gmail nests multipart/alternative and multipart/mixed arbitrarily deep -
    walk the tree looking for the first text/plain part."""
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        return _b64url_decode(payload["body"]["data"])
    for part in payload.get("parts", []):
        text = _extract_plain_text(part)
        if text:
            return text
    return ""
