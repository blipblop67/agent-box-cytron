"""
Proves the actual bug this exists for: accessing the hub via a .local
mDNS name or a raw LAN IP - the two ways this hub is normally reached on
a Pi - produces a redirect URI Google's own OAuth client setup silently
rejects. This checks the detection function directly against exactly the
hostnames a real deployment would hit, plus that the Settings/Account
pages actually surface the warning end-to-end.
Run with: python3 tests/test_google_oauth_warning.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-oauthwarn-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, google_oauth  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


def main():
    # --- the exact two patterns that block every Pi deployment by default ---
    local_warning = google_oauth.google_oauth_warning_for("http://agenthub.local:8811/api/email/auth/callback")
    assert local_warning is not None and "agenthub.local" in local_warning and "top private domain" in local_warning
    print(f"[ok] a .local mDNS address is flagged: \"{local_warning[:70]}...\"")

    ip_warning = google_oauth.google_oauth_warning_for("http://192.168.1.95:8811/api/email/auth/callback")
    assert ip_warning is not None and "192.168.1.95" in ip_warning and "top-level domain" in ip_warning
    print(f"[ok] a raw LAN IP is flagged: \"{ip_warning[:70]}...\"")

    # --- Google's actual loopback exceptions must NOT be flagged ---
    assert google_oauth.google_oauth_warning_for("http://localhost:8811/api/email/auth/callback") is None
    assert google_oauth.google_oauth_warning_for("http://127.0.0.1:8811/api/email/auth/callback") is None
    print("[ok] localhost and 127.0.0.1 (Google's real exceptions) are never flagged")

    # --- a real-looking domain, including a dynamic-DNS style one, is never flagged ---
    assert google_oauth.google_oauth_warning_for("https://myhub.duckdns.org:8811/api/email/auth/callback") is None
    assert google_oauth.google_oauth_warning_for("https://agenthub.example.com/api/email/auth/callback") is None
    print("[ok] a real domain (including a dynamic-DNS style one) is never flagged")

    # --- end to end: the Settings page surfaces this for a hub reached via a raw IP ---
    client = TestClient(app)
    headers = auth_headers(client, "Alex")
    # TestClient's default base_url doesn't look like a real deployment, so
    # explicitly point requests at a fake IP-style Host header the way a
    # real browser hitting the Pi's LAN IP would
    ip_client = TestClient(app, base_url="http://192.168.1.95:8811")
    ip_headers = auth_headers(ip_client, "Sam")
    settings = ip_client.get("/api/settings", headers=ip_headers).json()
    assert settings["google_oauth_redirect_warning"] is not None
    assert "192.168.1.95" in settings["google_oauth_redirect_warning"]
    print("[ok] the Settings page surfaces the warning when reached via a raw IP")

    # --- and doesn't when reached normally ---
    normal_settings = client.get("/api/settings", headers=headers).json()
    assert normal_settings["google_oauth_redirect_warning"] is None
    print("[ok] no warning shown when reached via a normal-looking host")

    # --- same on the personal Account settings ---
    account_settings = ip_client.get("/api/account/settings", headers=ip_headers).json()
    assert account_settings["google_oauth_redirect_warning"] is not None
    print("[ok] the Account page surfaces the same warning")

    print("\nAll Google OAuth redirect-warning smoke tests passed.")


if __name__ == "__main__":
    main()
