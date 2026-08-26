"""
Proves the actual point of this feature: once DuckDNS is configured, the
Google-OAuth-redirect-URI problem stops being something anyone has to
think about again. Covers saving credentials, an immediate manual update,
the background refresh job picking up an IP change on its own (the part
that matters most - surviving a DHCP renewal without anyone noticing),
and the Settings page warning switching from generic advice to a direct
"use this address" once a real fix is already in hand.
Run with: python3 tests/test_dynamic_dns.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-duckdns-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, scheduler  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()

_duckdns_calls = []


class FakeResponse:
    def __init__(self, text):
        self.text = text


def fake_duckdns_get(url, params=None, **kwargs):
    _duckdns_calls.append(dict(params))
    if params.get("token") == "wrong-token":
        return FakeResponse("KO")
    return FakeResponse(f"OK\n{params['ip']}")


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")  # admin

    # --- starts unconfigured ---
    settings = client.get("/api/settings", headers=headers).json()
    assert settings["duckdns_configured"] is False
    print("[ok] starts unconfigured")

    # --- a non-admin can't set it up ---
    sam_headers = auth_headers(client, "Sam")
    forbidden = client.put("/api/settings", headers=sam_headers, json={"duckdns_subdomain": "evil"})
    assert forbidden.status_code == 403
    print("[ok] only an admin can configure DuckDNS")

    # --- save credentials ---
    with patch("httpx.get", side_effect=fake_duckdns_get):
        saved = client.put("/api/settings", headers=headers, json={
            "duckdns_subdomain": "sirim-agenthub", "duckdns_token": "real-token-abc",
        }).json()
    assert saved["duckdns_subdomain"] == "sirim-agenthub"
    assert saved["duckdns_token_configured"] is True
    assert saved["duckdns_configured"] is True
    print("[ok] admin saved a subdomain + token")

    # --- manual "update now" actually calls DuckDNS with the right params ---
    with patch("app.dynamic_dns.detect_lan_ip", return_value="192.168.1.95"), \
         patch("httpx.get", side_effect=fake_duckdns_get):
        update_result = client.post("/api/settings/duckdns/update-now", headers=headers).json()
    assert update_result == {"domain": "sirim-agenthub.duckdns.org", "ip": "192.168.1.95"}
    last_call = _duckdns_calls[-1]
    assert last_call["domains"] == "sirim-agenthub" and last_call["token"] == "real-token-abc" and last_call["ip"] == "192.168.1.95"
    print(f"[ok] update-now correctly told DuckDNS to point {last_call['domains']}.duckdns.org at {last_call['ip']}")

    settings_after = client.get("/api/settings", headers=headers).json()
    assert settings_after["duckdns_last_updated_ip"] == "192.168.1.95"
    assert settings_after["duckdns_last_updated_at"] is not None
    print("[ok] last-updated status is recorded and visible")

    # --- THE ACTUAL POINT: the background refresh job survives an IP change on its
    # own, with nobody touching anything - this is what "permanent fix" means ---
    with patch("app.dynamic_dns.detect_lan_ip", return_value="192.168.1.200"), \
         patch("httpx.get", side_effect=fake_duckdns_get):
        scheduler._refresh_duckdns()  # exactly what the periodic background job calls
    settings_after_dhcp_change = client.get("/api/settings", headers=headers).json()
    assert settings_after_dhcp_change["duckdns_last_updated_ip"] == "192.168.1.200"
    print("[ok] the background refresh job updated DuckDNS automatically after a simulated IP change (DHCP renewal)")

    # --- a wrong token gives a clear error, not silent failure ---
    client.put("/api/settings", headers=headers, json={"duckdns_subdomain": "sirim-agenthub", "duckdns_token": "wrong-token"})
    with patch("httpx.get", side_effect=fake_duckdns_get):
        bad_update = client.post("/api/settings/duckdns/update-now", headers=headers)
    assert bad_update.status_code == 400
    print("[ok] a rejected update gives a clear error")

    # --- the background job doesn't crash the scheduler when DuckDNS rejects it -
    # it should just record the error and move on ---
    with patch("httpx.get", side_effect=fake_duckdns_get):
        scheduler._refresh_duckdns()  # must not raise
    error_settings = client.get("/api/settings", headers=headers).json()
    assert error_settings["duckdns_last_error"] != ""
    print("[ok] a failed background refresh records the error instead of crashing anything")

    # --- fix the token, confirm the warning banner references the DuckDNS domain
    # directly instead of generic advice, once one is actually configured ---
    with patch("httpx.get", side_effect=fake_duckdns_get):
        client.put("/api/settings", headers=headers, json={"duckdns_subdomain": "sirim-agenthub", "duckdns_token": "real-token-abc"})
        client.post("/api/settings/duckdns/update-now", headers=headers)

    ip_client = TestClient(app, base_url="http://192.168.1.95:8811")
    ip_headers = auth_headers(ip_client, "Jordan")
    ip_settings = ip_client.get("/api/settings", headers=ip_headers).json()
    assert ip_settings["google_oauth_redirect_warning"] is not None
    assert "sirim-agenthub.duckdns.org" in ip_settings["google_oauth_redirect_warning"]
    assert "8811" in ip_settings["google_oauth_redirect_warning"]
    print(f"[ok] the warning now points directly at the real fix: \"{ip_settings['google_oauth_redirect_warning'][:80]}...\"")

    print("\nAll DuckDNS smoke tests passed.")


if __name__ == "__main__":
    main()
