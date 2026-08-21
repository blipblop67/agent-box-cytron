"""
Covers registration, login, wrong-password rejection, lockout after repeated
failures, claiming a pre-existing passwordless account (the upgrade path for
a hub that used to only ask for a name), admin password reset, self-service
password change, logout, and that password hashes are never returned by the
API. Run with: python3 tests/test_auth.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-auth-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, security  # noqa: E402
from app.main import app  # noqa: E402

db.init_db()


def main():
    client = TestClient(app)

    # --- registering a brand new account (first user -> admin) ---
    resp = client.post("/api/auth/authenticate", json={"name": "Alex", "password": "correct-horse-1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    token = body["token"]
    assert body["user"]["role"] == "admin"
    print("[ok] registered a new account, first user is admin, got a session token")

    # --- the token actually works for authenticated requests ---
    me = client.get("/api/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["name"] == "Alex"
    print("[ok] session token authenticates subsequent requests")

    # --- no token at all is rejected ---
    denied = client.get("/api/me")
    assert denied.status_code == 401
    print("[ok] requests without a session token are rejected")

    # --- garbage token is rejected, not a 500 ---
    denied2 = client.get("/api/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert denied2.status_code == 401
    print("[ok] an invalid session token is rejected cleanly")

    # --- logging back in with the right password reuses the same account ---
    resp2 = client.post("/api/auth/authenticate", json={"name": "Alex", "password": "correct-horse-1"})
    assert resp2.status_code == 200
    assert resp2.json()["user"]["id"] == body["user"]["id"]
    assert resp2.json()["user"]["role"] == "admin"  # still admin, not re-bootstrapped
    print("[ok] logging in again with the right password returns the same account")

    # --- wrong password is rejected ---
    wrong = client.post("/api/auth/authenticate", json={"name": "Alex", "password": "totally-wrong"})
    assert wrong.status_code == 401
    print("[ok] wrong password is rejected")

    # --- password hash is never returned anywhere ---
    assert "password" not in str(resp2.json()).lower().replace("password\":", "")  # crude but effective
    headers = {"Authorization": f"Bearer {token}"}
    team = client.get("/api/users", headers=headers).json()
    assert all("password_hash" not in u and "password" not in u for u in team)
    print("[ok] password hashes never appear in any API response")

    # --- a second person registers -> becomes a regular member ---
    resp3 = client.post("/api/auth/authenticate", json={"name": "Sam", "password": "sams-password-1"})
    assert resp3.json()["user"]["role"] == "member"
    sam_headers = {"Authorization": f"Bearer {resp3.json()['token']}"}
    print("[ok] second person to register is a regular member, not admin")

    # --- lockout after repeated failed attempts ---
    for _ in range(5):
        client.post("/api/auth/authenticate", json={"name": "Sam", "password": "wrong-again"})
    locked = client.post("/api/auth/authenticate", json={"name": "Sam", "password": "sams-password-1"})
    assert locked.status_code == 429
    print("[ok] repeated failed attempts lock out further tries, even with the correct password")
    security.clear_attempts("sam")  # unstick it for the rest of this test

    # --- claiming a pre-existing passwordless account (the pre-auth upgrade path) ---
    db.create_user("priya", "Priya", password_hash=None, role="member")  # simulates an old-style account
    claim = client.post("/api/auth/authenticate", json={"name": "Priya", "password": "priyas-new-password"})
    assert claim.status_code == 200
    assert claim.json()["user"]["id"] == "priya"
    relogin = client.post("/api/auth/authenticate", json={"name": "Priya", "password": "priyas-new-password"})
    assert relogin.status_code == 200
    wrong_after_claim = client.post("/api/auth/authenticate", json={"name": "Priya", "password": "totally-wrong-guess"})
    assert wrong_after_claim.status_code == 401
    print("[ok] a pre-existing passwordless account can be claimed, and is then password-protected")

    # --- self-service password change ---
    changed = client.post(
        "/api/auth/change-password", headers=sam_headers,
        json={"current_password": "sams-password-1", "new_password": "sams-new-password-2"},
    )
    assert changed.status_code == 200
    # old session was invalidated by the password change
    stale = client.get("/api/me", headers=sam_headers)
    assert stale.status_code == 401
    relogged = client.post("/api/auth/authenticate", json={"name": "Sam", "password": "sams-new-password-2"})
    assert relogged.status_code == 200
    print("[ok] self-service password change invalidates old sessions and the new password works")

    # --- admin can reset someone else's password; a non-admin can't ---
    sam_headers2 = {"Authorization": f"Bearer {relogged.json()['token']}"}
    forbidden = client.patch("/api/users/priya/password", headers=sam_headers2, json={"new_password": "hijacked!"})
    assert forbidden.status_code == 403
    admin_reset = client.patch("/api/users/priya/password", headers=headers, json={"new_password": "admin-set-this-1"})
    assert admin_reset.status_code == 200
    priya_new_login = client.post("/api/auth/authenticate", json={"name": "Priya", "password": "admin-set-this-1"})
    assert priya_new_login.status_code == 200
    print("[ok] an admin can reset another user's password; a non-admin cannot")

    # --- logout invalidates the token ---
    logout_resp = client.post("/api/auth/logout", headers=headers)
    assert logout_resp.status_code == 200
    after_logout = client.get("/api/me", headers=headers)
    assert after_logout.status_code == 401
    print("[ok] logout invalidates the session token")

    print("\nAll auth smoke tests passed.")


if __name__ == "__main__":
    main()
