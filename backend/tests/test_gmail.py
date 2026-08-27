"""
Exercises the Gmail integration - send, list, read, reply - via the hub-wide
service account, without touching real Google servers. httpx.get/post are
patched with fake responses shaped like Google's actual APIs (both the
JWT-bearer token exchange and the Gmail REST calls), so this checks our
request construction and response parsing, not Google's uptime.
Run with: python3 tests/test_gmail.py
"""
import base64
import json as json_module
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-gmail-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SERVICE_ACCOUNT_KEY = json_module.dumps({
    "type": "service_account",
    "client_email": "sa@sirim-coc-agent.iam.gserviceaccount.com",
    "private_key": _private_key.private_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode(),
    "private_key_id": "fake-key-id",
})


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"fake HTTP {self.status_code}: {self._json}")

    def json(self):
        return self._json


def _b64url(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def fake_post(url, data=None, json=None, **kwargs):
    if url == "https://oauth2.googleapis.com/token":
        return FakeResponse({"access_token": "impersonated-token", "expires_in": 3600})
    if url.endswith("/messages/send"):
        return FakeResponse({"id": "sent-msg-1", "threadId": json.get("threadId", "new-thread-1")})
    raise AssertionError(f"unexpected POST {url} data={data} json={json}")


def fake_get(url, headers=None, params=None, **kwargs):
    assert headers["Authorization"] == "Bearer impersonated-token"

    if url.endswith("/messages") and params and "maxResults" in params:
        return FakeResponse({"messages": [{"id": "msg-abc"}]})

    if url.endswith("/messages/msg-abc") and params.get("format") == "metadata":
        return FakeResponse({
            "id": "msg-abc", "threadId": "thread-abc", "snippet": "Hey, quick question...",
            "payload": {"headers": [
                {"name": "From", "value": "Sam <sam@example.com>"},
                {"name": "To", "value": "priya@example.com"},
                {"name": "Subject", "value": "Quick question"},
                {"name": "Date", "value": "Tue, 28 Jul 2026 10:00:00 -0700"},
                {"name": "Message-ID", "value": "<orig-msg-id@mail.gmail.com>"},
            ]},
        })

    if url.endswith("/messages/msg-abc") and params.get("format") == "full":
        plain_body = "Hey, do you have the Q3 numbers ready?"
        return FakeResponse({
            "id": "msg-abc", "threadId": "thread-abc", "snippet": "Hey, quick question...",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Sam <sam@example.com>"},
                    {"name": "To", "value": "priya@example.com"},
                    {"name": "Subject", "value": "Quick question"},
                    {"name": "Date", "value": "Tue, 28 Jul 2026 10:00:00 -0700"},
                    {"name": "Message-ID", "value": "<orig-msg-id@mail.gmail.com>"},
                ],
                "mimeType": "multipart/alternative",
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _b64url(plain_body)}},
                    {"mimeType": "text/html", "body": {"data": _b64url(f"<p>{plain_body}</p>")}},
                ],
            },
        })

    raise AssertionError(f"unexpected GET {url} params={params}")


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Priya")

    # --- before any service account is configured, calls fail with a clear error ---
    unconfigured = client.post("/api/email/send", headers=headers, json={"to": "x@example.com", "subject": "s", "body": "b"})
    assert unconfigured.status_code == 400 and "service account" in unconfigured.text.lower()
    print("[ok] a clear error, not a raw failure, when no service account is configured yet")

    client.put("/api/settings", headers=headers, json={"google_service_account_key": SERVICE_ACCOUNT_KEY})
    print("[ok] admin configured the service account key")

    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        sent = client.post(
            "/api/email/send", headers=headers,
            json={"to": "sam@example.com", "subject": "Hello", "body": "Hi Sam!", "impersonate": "priya@cytron.io"},
        ).json()
    assert sent["id"] == "sent-msg-1"
    print("[ok] sent a new email, impersonating a Workspace address")

    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        messages = client.get(
            "/api/email/messages", headers=headers, params={"max_results": 5, "impersonate": "priya@cytron.io"},
        ).json()
    assert len(messages) == 1 and messages[0]["subject"] == "Quick question"
    print(f"[ok] listed {len(messages)} message(s): \"{messages[0]['subject']}\" from {messages[0]['from']}")

    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        full = client.get("/api/email/messages/msg-abc", headers=headers, params={"impersonate": "priya@cytron.io"}).json()
    assert full["body"] == "Hey, do you have the Q3 numbers ready?"
    print(f"[ok] read full body via MIME parsing: \"{full['body']}\"")

    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        reply = client.post(
            "/api/email/messages/msg-abc/reply", headers=headers,
            json={"body": "Yes! Sending them over now.", "impersonate": "priya@cytron.io"},
        ).json()
    assert reply["threadId"] == "thread-abc"
    print("[ok] replied on the same thread")

    print("\nAll Gmail smoke tests passed.")


if __name__ == "__main__":
    main()
