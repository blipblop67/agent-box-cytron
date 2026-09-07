"""
Proves the Tailscale integration end to end - joining, live status, and
leaving - by mocking subprocess.run rather than needing a real tailscale
binary in this sandbox. Also proves the specific design choice that
makes this different from DuckDNS: the auth key is never persisted
anywhere, unlike DuckDNS's token which is stored and reused.
Run with: python3 tests/test_tailscale.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-tailscale-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, tailscale_client  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


def fake_completed(returncode=0, stdout="", stderr=""):
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")  # admin
    sam_headers = auth_headers(client, "Sam")  # non-admin

    # --- not installed: settings correctly reflects this, status is honest about it ---
    with patch.object(tailscale_client, "is_installed", return_value=False):
        settings = client.get("/api/settings", headers=headers).json()
        assert settings["tailscale_installed"] is False
        status = client.get("/api/settings/tailscale/status", headers=headers).json()
        assert status == {"connected": False, "installed": False}
    print("[ok] correctly reports not installed, both in Settings and via live status")

    # --- installed, not yet joined ---
    with patch.object(tailscale_client, "is_installed", return_value=True):
        settings = client.get("/api/settings", headers=headers).json()
        assert settings["tailscale_installed"] is True
    print("[ok] Settings reflects installed=True once the binary exists")

    # --- only an admin can join ---
    join_body = {"auth_key": "tskey-auth-fake1234567890"}
    with patch.object(tailscale_client, "is_installed", return_value=True):
        forbidden = client.post("/api/settings/tailscale/join", headers=sam_headers, json=join_body)
    assert forbidden.status_code == 403
    print("[ok] only an admin can join a tailnet")

    # --- successful join: correct command, correct parsing of the resulting status ---
    status_json = """{"Self": {"Online": true, "DNSName": "agenthub-a3f9.tail1234.ts.net.", "TailscaleIPs": ["100.64.12.3"]}, "CurrentTailnet": {"Name": "example.ts.net"}}"""
    captured_cmds = []

    def fake_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        if cmd[:2] == ["sudo", "-n"] and "up" in cmd:
            return fake_completed(0)
        if cmd[-1] == "--json" or (len(cmd) > 1 and cmd[1] == "status"):
            return fake_completed(0, stdout=status_json)
        return fake_completed(0)

    with patch.object(tailscale_client, "is_installed", return_value=True), \
         patch("subprocess.run", side_effect=fake_run):
        join_result = client.post("/api/settings/tailscale/join", headers=headers, json={
            "auth_key": "tskey-auth-fake1234567890", "hostname": "agenthub-a3f9",
        }).json()

    assert join_result["connected"] is True
    assert join_result["hostname"] == "agenthub-a3f9.tail1234.ts.net"
    assert join_result["tailscale_ip"] == "100.64.12.3"
    assert join_result["tailnet"] == "example.ts.net"
    print(f"[ok] joined successfully: {join_result['hostname']} ({join_result['tailscale_ip']})")

    up_cmd = next(c for c in captured_cmds if "up" in c)
    assert "--authkey=tskey-auth-fake1234567890" in up_cmd
    assert "--hostname=agenthub-a3f9" in up_cmd
    print("[ok] the auth key and hostname were passed through to the real tailscale command correctly")

    # --- THE KEY DESIGN CHECK: the auth key is never persisted anywhere,
    # unlike DuckDNS's token which IS stored for reuse ---
    with db.get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM hub_settings").fetchall()
        all_values = " ".join(f"{r['key']}={r['value']}" for r in rows)
    assert "tskey-auth-fake1234567890" not in all_values
    print("[ok] the auth key was never written to the database - confirmed by checking every stored setting")

    # --- a rejected key gives a clean error, not a raw subprocess dump ---
    def fake_run_rejected(cmd, **kwargs):
        if "up" in cmd:
            return fake_completed(1, stderr="tailscale up: key expired or revoked")
        return fake_completed(0)

    with patch.object(tailscale_client, "is_installed", return_value=True), \
         patch("subprocess.run", side_effect=fake_run_rejected):
        bad_join = client.post("/api/settings/tailscale/join", headers=headers, json={"auth_key": "tskey-bad"})
    assert bad_join.status_code == 400
    assert "expired or revoked" in bad_join.json()["detail"]
    print(f"[ok] a rejected key gives a clean error: {bad_join.json()['detail']!r}")

    # --- a missing sudoers rule gets a specific, actionable error ---
    def fake_run_no_sudo(cmd, **kwargs):
        if "up" in cmd:
            return fake_completed(1, stderr="sudo: a password is required")
        return fake_completed(0)

    with patch.object(tailscale_client, "is_installed", return_value=True), \
         patch("subprocess.run", side_effect=fake_run_no_sudo):
        no_sudo = client.post("/api/settings/tailscale/join", headers=headers, json={"auth_key": "tskey-x"})
    assert no_sudo.status_code == 400
    assert "sudoers" in no_sudo.json()["detail"].lower()
    print("[ok] a missing sudoers rule gives a specific, actionable error, not a generic failure")

    # --- leave: only an admin, and it actually calls the right command ---
    forbidden_leave = client.post("/api/settings/tailscale/leave", headers=sam_headers)
    assert forbidden_leave.status_code == 403

    leave_cmds = []
    with patch.object(tailscale_client, "is_installed", return_value=True), \
         patch("subprocess.run", side_effect=lambda cmd, **kw: (leave_cmds.append(cmd), fake_completed(0))[1]):
        leave_result = client.post("/api/settings/tailscale/leave", headers=headers).json()
    assert leave_result == {"ok": True}
    assert any("logout" in c for c in leave_cmds[0])
    print("[ok] leave correctly calls tailscale logout, admin-only")

    print("\nAll Tailscale smoke tests passed.")


if __name__ == "__main__":
    main()
