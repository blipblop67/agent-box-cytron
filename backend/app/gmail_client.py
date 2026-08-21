"""
Thin wrapper around the Gmail REST API v1 - send, list, read, and reply.
Raw REST + stdlib `email.mime` rather than the official Google client library,
for the same "keep it small and readable" reason as gmail_oauth.py.
"""
import base64
from email.mime.text import MIMEText
from email.utils import parseaddr

import httpx

from . import gmail_tokens

API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _headers(user_id: str) -> dict:
    token = gmail_tokens.get_valid_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def _b64url_encode(raw_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(raw_bytes).decode()


def _b64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode(errors="ignore")


def send_email(user_id: str, to: str, subject: str, body: str, *,
                thread_id: str | None = None, in_reply_to: str | None = None,
                references: str | None = None) -> dict:
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

    resp = httpx.post(f"{API_BASE}/messages/send", headers=_headers(user_id), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def list_messages(user_id: str, query: str = "", max_results: int = 10) -> list[dict]:
    """Cheap listing: headers + snippet only (format=metadata), not the full body -
    good for scanning an inbox without pulling every message's full content."""
    params = {"maxResults": max_results}
    if query:
        params["q"] = query
    resp = httpx.get(f"{API_BASE}/messages", headers=_headers(user_id), params=params, timeout=30)
    resp.raise_for_status()
    ids = [m["id"] for m in resp.json().get("messages", [])]
    return [_get_message_metadata(user_id, mid) for mid in ids]


def _get_message_metadata(user_id: str, message_id: str) -> dict:
    resp = httpx.get(
        f"{API_BASE}/messages/{message_id}",
        headers=_headers(user_id),
        params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date", "Message-ID"]},
        timeout=30,
    )
    resp.raise_for_status()
    return _parse_message(resp.json(), include_body=False)


def get_message(user_id: str, message_id: str) -> dict:
    """Full read: headers plus the plain-text body, for when an agent actually
    needs to read what an email says, not just its subject line."""
    resp = httpx.get(
        f"{API_BASE}/messages/{message_id}",
        headers=_headers(user_id),
        params={"format": "full"},
        timeout=30,
    )
    resp.raise_for_status()
    return _parse_message(resp.json(), include_body=True)


def reply_to_message(user_id: str, message_id: str, body: str) -> dict:
    original = get_message(user_id, message_id)
    to_address = parseaddr(original["from"])[1]
    subject = original["subject"] or ""
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"
    return send_email(
        user_id, to=to_address, subject=subject, body=body,
        thread_id=original["thread_id"],
        in_reply_to=original["message_id_header"],
        references=original["message_id_header"],
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
