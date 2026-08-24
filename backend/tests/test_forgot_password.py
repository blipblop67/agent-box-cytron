"""
Covers the full email-based recovery flow: request a reset (mocked SMTP,
capturing the actual link the "email" would contain, the same way a real
person would click it from their inbox), use that link's token to set a
new password, and confirm the old password stops working. Also covers the
security properties that matter most here: the response is identical
whether or not the account/email exists (no user enumeration), a token
only works once, an expired token is rejected, and requests are rate
limited.
Run with: python3 tests/test_forgot_password.py
"""
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-forgotpw-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, security  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


def _capture_sent_email():
    """Mocks smtplib.SMTP so email_sender.py's send_email() succeeds without
    touching a real server, and returns a mutable dict that gets filled in
    with what was "sent" once the call happens."""
    sent = {}
    mock_server = MagicMock()

    def fake_send_message(message):
        sent["to"] = message["To"]
        sent["subject"] = message["Subject"]
        sent["body"] = message.get_payload()

    mock_server.send_message.side_effect = fake_send_message
    mock_smtp_cls = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_server
    return sent, mock_smtp_cls


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")  # admin

    # --- configure SMTP (admin-only) ---
    smtp_config = client.put("/api/settings", headers=headers, json={
        "smtp_host": "smtp.example.com", "smtp_port": "587", "smtp_username": "hub@example.com",
        "smtp_password": "app-password-123", "smtp_from_address": "hub@example.com", "smtp_use_tls": True,
    }).json()
    assert smtp_config["smtp_configured"] is True
    assert smtp_config["smtp_password_configured"] is True
    print("[ok] admin configured SMTP settings")

    # --- non-admin can't touch SMTP settings ---
    sam_headers = auth_headers(client, "Sam")
    forbidden = client.put("/api/settings", headers=sam_headers, json={"smtp_host": "evil.example.com"})
    assert forbidden.status_code == 403
    print("[ok] only an admin can change SMTP settings")

    # --- Sam sets a recovery email on the Account page ---
    email_update = client.patch("/api/me/email", headers=sam_headers, json={"email": "sam@example.com"}).json()
    assert email_update["email"] == "sam@example.com"
    me = client.get("/api/me", headers=sam_headers).json()
    assert me["email"] == "sam@example.com"
    print("[ok] Sam set a recovery email")

    # --- an invalid email is rejected ---
    bad_email = client.patch("/api/me/email", headers=sam_headers, json={"email": "not-an-email"})
    assert bad_email.status_code == 400
    print("[ok] an invalid email format is rejected")

    # --- THE ACTUAL POINT: forgot-password sends an email, the link in it works ---
    sent, mock_smtp_cls = _capture_sent_email()
    with patch("smtplib.SMTP", mock_smtp_cls):
        resp = client.post("/api/auth/forgot-password", json={"name": "Sam"})
    assert resp.status_code == 200
    generic_message = resp.json()["message"]
    assert sent["to"] == "sam@example.com"
    assert sent["subject"] == "Reset your Agent Hub password"
    print(f"[ok] a reset email was sent to sam@example.com: \"{sent['subject']}\"")

    match = re.search(r"reset-password\?token=(\S+)", sent["body"])
    assert match, f"no reset link found in the email body:\n{sent['body']}"
    token = match.group(1)
    print("[ok] extracted the reset token from the email body, the way a person would click the link")

    # --- use the token to set a new password ---
    reset_resp = client.post("/api/auth/reset-password", json={"token": token, "new_password": "brand-new-pw-789"})
    assert reset_resp.status_code == 200
    print("[ok] reset the password using the token from the email")

    # --- old password rejected, new one works ---
    old_fails = client.post("/api/auth/authenticate", json={"name": "Sam", "password": "test-password-123"})
    assert old_fails.status_code == 401
    new_works = client.post("/api/auth/authenticate", json={"name": "Sam", "password": "brand-new-pw-789"})
    assert new_works.status_code == 200
    print("[ok] the old password is rejected, the new one works")

    # --- the token can't be reused ---
    reuse_attempt = client.post("/api/auth/reset-password", json={"token": token, "new_password": "yet-another-pw"})
    assert reuse_attempt.status_code == 400
    print("[ok] the same token can't be used twice")

    # --- a made-up token is rejected the same way ---
    fake_token_attempt = client.post("/api/auth/reset-password", json={"token": "totally-made-up", "new_password": "whatever-123"})
    assert fake_token_attempt.status_code == 400
    print("[ok] a made-up token is rejected")

    # --- NO USER ENUMERATION: a nonexistent name gets the exact same response ---
    sent2, mock_smtp_cls2 = _capture_sent_email()
    with patch("smtplib.SMTP", mock_smtp_cls2):
        nonexistent_resp = client.post("/api/auth/forgot-password", json={"name": "NobodyByThisName"})
    assert nonexistent_resp.status_code == 200
    assert nonexistent_resp.json()["message"] == generic_message
    assert "to" not in sent2  # no email was actually attempted
    print("[ok] a nonexistent account gets the identical generic response, no email sent - can't be enumerated")

    # --- an existing account with NO email set also gets the same generic response ---
    auth_headers(client, "Jordan")  # registers Jordan, no email set
    sent3, mock_smtp_cls3 = _capture_sent_email()
    with patch("smtplib.SMTP", mock_smtp_cls3):
        no_email_resp = client.post("/api/auth/forgot-password", json={"name": "Jordan"})
    assert no_email_resp.status_code == 200
    assert no_email_resp.json()["message"] == generic_message
    assert "to" not in sent3
    print("[ok] an account with no recovery email set also gets the generic response, no email sent")

    # --- rate limiting: repeated requests for the same name eventually stop sending ---
    auth_headers(client, "Riley")
    client.patch("/api/me/email", headers=auth_headers(client, "Riley"), json={"email": "riley@example.com"})
    sends = []
    for i in range(5):
        s, cls = _capture_sent_email()
        with patch("smtplib.SMTP", cls):
            client.post("/api/auth/forgot-password", json={"name": "Riley"})
        sends.append("to" in s)
    assert sends[0] is True and sends[1] is True and sends[2] is True  # first 3 within the limit
    assert sends[3] is False and sends[4] is False  # 4th and 5th are throttled
    print(f"[ok] rate limiting kicks in after 3 requests: {sends}")

    # --- a token expires ---
    expired_user_headers = auth_headers(client, "Casey")
    client.patch("/api/me/email", headers=expired_user_headers, json={"email": "casey@example.com"})
    expired_sent, expired_cls = _capture_sent_email()
    with patch("smtplib.SMTP", expired_cls):
        client.post("/api/auth/forgot-password", json={"name": "Casey"})
    expired_token = re.search(r"token=(\S+)", expired_sent["body"]).group(1)
    # simulate time passing past the 1-hour expiry by writing an already-expired row directly
    token_hash = security.hash_password_reset_token(expired_token)
    with db.get_conn() as conn:
        conn.execute("UPDATE password_reset_tokens SET expires_at = ? WHERE token_hash = ?", (time.time() - 10, token_hash))
    expired_attempt = client.post("/api/auth/reset-password", json={"token": expired_token, "new_password": "whatever-123"})
    assert expired_attempt.status_code == 400
    print("[ok] an expired token is rejected")

    print("\nAll forgot-password smoke tests passed.")


if __name__ == "__main__":
    main()
