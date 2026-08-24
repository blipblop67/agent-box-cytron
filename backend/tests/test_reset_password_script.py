"""
Runs reset_password.py as an actual subprocess with piped input - the same
way a locked-out admin would run it - rather than importing and mocking its
internals, since the whole point is that this exact script, run exactly
this way, has to work when someone's genuinely locked out.
Run with: python3 tests/test_reset_password_script.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DATA_DIR = tempfile.mkdtemp(prefix="agent-hub-resetscript-test-")
os.environ["AGENT_HUB_DATA_DIR"] = DATA_DIR  # must happen before importing anything from app -
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # config.py reads this at import time

from app import db, security  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPT_PATH = BACKEND_DIR / "reset_password.py"


def main():
    env = {**os.environ, "AGENT_HUB_DATA_DIR": DATA_DIR}

    # set up an account the normal way, with a known starting password
    db.init_db()
    db.create_user("alex", "Alex", security.hash_password("original-password-123"), role="admin")
    db.create_user("sam", "Sam", security.hash_password("sams-password-1"), role="member")
    print("[ok] set up two accounts the normal way")

    # --- run the actual script as a real subprocess, piping in the choices ---
    stdin_input = "alex\ny\nbrand-new-password-456\nbrand-new-password-456\n"
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=stdin_input, capture_output=True, text=True, env=env, cwd=str(BACKEND_DIR), timeout=30,
    )
    assert result.returncode == 0, f"script failed:\n{result.stdout}\n{result.stderr}"
    assert "Alex" in result.stdout and "admin" in result.stdout  # the account listing showed up
    assert "Done." in result.stdout
    print("[ok] the script ran successfully as a real subprocess and reported success")

    # --- prove it through the actual running app, not just by inspecting the DB ---
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)

    old_password_attempt = client.post("/api/auth/authenticate", json={"name": "Alex", "password": "original-password-123"})
    assert old_password_attempt.status_code == 401
    print("[ok] the OLD password is rejected by the real running app")

    new_password_attempt = client.post("/api/auth/authenticate", json={"name": "Alex", "password": "brand-new-password-456"})
    assert new_password_attempt.status_code == 200
    assert new_password_attempt.json()["user"]["role"] == "admin"  # role was preserved, not reset
    print("[ok] the NEW password works and the account is still admin")

    # --- the untouched account (Sam) is completely unaffected ---
    sam_still_works = client.post("/api/auth/authenticate", json={"name": "Sam", "password": "sams-password-1"})
    assert sam_still_works.status_code == 200
    print("[ok] a different account not chosen for reset is completely untouched")

    # --- cancelling (answering 'n' to the confirmation) changes nothing ---
    cancel_input = "sam\nn\n"
    cancel_result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        input=cancel_input, capture_output=True, text=True, env=env, cwd=str(BACKEND_DIR), timeout=30,
    )
    assert cancel_result.returncode == 0
    assert "Cancelled" in cancel_result.stdout
    sam_unchanged = client.post("/api/auth/authenticate", json={"name": "Sam", "password": "sams-password-1"})
    assert sam_unchanged.status_code == 200
    print("[ok] answering 'no' to the confirmation prompt changes nothing")

    print("\nAll reset_password.py smoke tests passed.")


if __name__ == "__main__":
    main()
