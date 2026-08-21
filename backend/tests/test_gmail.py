"""
Exercises the whole Gmail integration - connect, send, list, read, reply -
without touching real Google servers or needing real OAuth credentials.
httpx.get/post are patched with fake responses shaped like Google's actual API,
so this checks our request construction and response parsing, not Google's
uptime. Run with: python3 tests/test_gmail.py
"""
import base64
import os
import sys
import tempfile
from email.mime.text import MIMEText
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-gmail-test-"))
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost:8811/api/email/auth/callback")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


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
        if data["grant_type"] == "authorization_code":
            assert data["code"] == "fake-auth-code"
            return FakeResponse({"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600})
        if data["grant_type"] == "refresh_token":
            assert data["refresh_token"] == "rt-1"
            return FakeResponse({"access_token": "at-fresh", "expires_in": 3600})
    if url.endswith("/messages/send"):
        return FakeResponse({"id": "sent-msg-1", "threadId": json.get("threadId", "new-thread-1")})
    raise AssertionError(f"unexpected POST {url} data={data} json={json}")


def fake_get(url, headers=None, params=None, **kwargs):
    if url == "https://www.googleapis.com/oauth2/v3/userinfo":
        assert headers["Authorization"] == "Bearer at-1"
        return FakeResponse({"email": "priya@example.com"})

    if url.endswith("/messages") and "q" not in (params or {}) or (params and "maxResults" in params and "q" in params):
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
    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        client = TestClient(app)
        headers = auth_headers(client, "Priya")

        assert client.get("/api/email/status", headers=headers).json() == {"connected": False}
        print("[ok] starts disconnected")

        start = client.get("/api/email/auth/start", headers=headers).json()
        assert "accounts.google.com" in start["authorization_url"]
        assert "test-client-id" in start["authorization_url"]
        state = start["authorization_url"].split("state=")[1].split("&")[0]
        print(f"[ok] auth/start returned a valid Google authorization URL")

        callback = client.get(
            "/api/email/auth/callback",
            params={"code": "fake-auth-code", "state": state},
            follow_redirects=False,
        )
        assert callback.status_code in (302, 307), callback.status_code
        print("[ok] auth/callback exchanged the code and redirected")

        status = client.get("/api/email/status", headers=headers).json()
        assert status == {"connected": True, "account_email": "priya@example.com",
                           "connected_at": status["connected_at"]}
        print(f"[ok] now connected as {status['account_email']}")

        sent = client.post(
            "/api/email/send", headers=headers,
            json={"to": "sam@example.com", "subject": "Hello", "body": "Hi Sam!"},
        ).json()
        assert sent["id"] == "sent-msg-1"
        print("[ok] sent a new email")

        messages = client.get("/api/email/messages", headers=headers, params={"max_results": 5}).json()
        assert len(messages) == 1 and messages[0]["subject"] == "Quick question"
        print(f"[ok] listed {len(messages)} message(s): \"{messages[0]['subject']}\" from {messages[0]['from']}")

        full = client.get("/api/email/messages/msg-abc", headers=headers).json()
        assert full["body"] == "Hey, do you have the Q3 numbers ready?"
        print(f"[ok] read full body via MIME parsing: \"{full['body']}\"")

        reply = client.post(
            "/api/email/messages/msg-abc/reply", headers=headers,
            json={"body": "Yes! Sending them over now."},
        ).json()
        assert reply["threadId"] == "thread-abc"
        print("[ok] replied on the same thread")

        client.delete("/api/email/auth", headers=headers)
        assert client.get("/api/email/status", headers=headers).json() == {"connected": False}
        print("[ok] disconnect works")

        # --- error paths that used to be an unhandled 500 or a bare 422 ---
        denied = client.get("/api/email/auth/callback", params={"error": "access_denied", "state": "irrelevant"})
        assert denied.status_code == 400 and "test user" in denied.text
        print("[ok] Google 'access_denied' redirect shows a helpful page, not a 500")

        no_code = client.get("/api/email/auth/callback", params={"state": "irrelevant"})
        assert no_code.status_code == 400 and "authorization code" in no_code.text
        print("[ok] a callback with no code shows a helpful page, not a raw 422")

        bad_state = client.get("/api/email/auth/callback", params={"code": "x", "state": "not-a-real-state"})
        assert bad_state.status_code == 400 and "expired" in bad_state.text
        print("[ok] an unknown/expired state shows a helpful page")

    print("\nAll Gmail smoke tests passed.")


if __name__ == "__main__":
    main()
