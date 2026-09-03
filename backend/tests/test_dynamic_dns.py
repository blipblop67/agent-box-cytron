"""
Proves the actual point of this feature: once DuckDNS is configured, the
hub is reachable at a real DNS name even on networks that block mDNS.
Covers saving credentials, an immediate manual update, and the background
refresh job picking up an IP change on its own (the part that matters
most - surviving a DHCP renewal without anyone noticing).
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
            "duckdns_subdomain": "agenthub-a3f9c1e2", "duckdns_token": "real-token-abc",
        }).json()
    assert saved["duckdns_subdomain"] == "agenthub-a3f9c1e2"
    assert saved["duckdns_token_configured"] is True
    assert saved["duckdns_configured"] is True
    print("[ok] admin saved a subdomain + token")

    # --- manual "update now" actually calls DuckDNS with the right params ---
    with patch("app.dynamic_dns.detect_lan_ip", return_value="192.168.1.95"), \
         patch("httpx.get", side_effect=fake_duckdns_get):
        update_result = client.post("/api/settings/duckdns/update-now", headers=headers).json()
    assert update_result == {"ok": True, "domain": "agenthub-a3f9c1e2.duckdns.org", "ip": "192.168.1.95"}
    last_call = _duckdns_calls[-1]
    assert last_call["domains"] == "agenthub-a3f9c1e2" and last_call["token"] == "real-token-abc" and last_call["ip"] == "192.168.1.95"
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
    client.put("/api/settings", headers=headers, json={"duckdns_subdomain": "agenthub-a3f9c1e2", "duckdns_token": "wrong-token"})
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

    # --- if DuckDNS was never configured at all, the background job is a silent
    # no-op every 5 minutes, not a wasted network call ---
    from app import hub_settings
    with patch.object(hub_settings, "get_duckdns_credentials", return_value=None), \
         patch("httpx.get", side_effect=fake_duckdns_get) as mock_get_unconfigured:
        scheduler._refresh_duckdns()
    assert mock_get_unconfigured.call_count == 0
    print("[ok] the background job makes zero network calls when DuckDNS isn't configured")

    print("\nAll DuckDNS smoke tests passed.")


if __name__ == "__main__":
    main()
