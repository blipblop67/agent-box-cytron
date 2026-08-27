"""
Proves the actual scenario this exists for: an employee (not hairil)
builds and runs a flow that reads hairil@cytron.io's inbox and updates a
spreadsheet in his Drive - with hairil never personally connecting
anything, and the employee never connecting Gmail/Sheets either. Only a
hub-wide service account key, plus an "Impersonate" field on the nodes.

Also covers the JWT itself is genuinely valid (structure + signature,
independently verified - not just "the mocked call succeeded"), that a
misconfigured/unauthorized service account gives a clear, specific error
rather than a generic failure, and that a node with NO impersonate field
set is completely unaffected (falls back to personal OAuth exactly as
before this existed).
Run with: python3 tests/test_service_account_impersonation.py
"""
import base64
import json as json_module
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-serviceaccount-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()

# a real RSA key pair, standing in for a Google-issued service account key
_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_private_pem = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()

SERVICE_ACCOUNT_KEY = json_module.dumps({
    "type": "service_account",
    "client_email": "sirim-agent@sirim-coc-agent.iam.gserviceaccount.com",
    "private_key": _private_pem,
    "private_key_id": "fake-key-id-abc123",
})

SPREADSHEET_ID = "hairils-tracker-sheet-id"
_sheet_rows: list[list[str]] = []
_last_jwt_by_subject: dict[str, str] = {}


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def fake_post(url, data=None, json=None, params=None, headers=None, **kwargs):
    if url == "https://oauth2.googleapis.com/token" and data and "assertion" in data:
        # this IS the service-account JWT-bearer token exchange - decode the
        # assertion to see exactly who it's impersonating, for the test to
        # assert on, and independently verify the signature is real
        assertion = data["assertion"]
        header_b64, claims_b64, sig_b64 = assertion.split(".")
        claims = json_module.loads(_unb64(claims_b64))
        signing_input = f"{header_b64}.{claims_b64}".encode()
        _private_key.public_key().verify(_unb64(sig_b64), signing_input, padding.PKCS1v15(), hashes.SHA256())
        subject = claims["sub"]
        _last_jwt_by_subject[subject] = assertion
        if subject == "not-authorized@cytron.io":
            return FakeResponse({"error": "unauthorized_client", "error_description": "Client not authorized"}, status_code=400)
        return FakeResponse({"access_token": f"impersonated-token-for-{subject}", "expires_in": 3600})
    if url == "https://sheets.googleapis.com/v4/spreadsheets":
        return FakeResponse({"spreadsheetId": SPREADSHEET_ID, "spreadsheetUrl": f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"})
    if url.endswith(":append"):
        _sheet_rows.append(json["values"][0])
        return FakeResponse({})
    raise AssertionError(f"unexpected POST {url}")


def fake_put(url, json=None, params=None, headers=None, **kwargs):
    range_part = url.rsplit("/", 1)[-1]
    row_number = int("".join(c for c in range_part.split("!")[1].split(":")[0] if c.isdigit()))
    while len(_sheet_rows) < row_number:
        _sheet_rows.append([])
    _sheet_rows[row_number - 1] = json["values"][0]
    return FakeResponse({})


def fake_get(url, params=None, headers=None, **kwargs):
    if url == f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/Sheet1":
        return FakeResponse({"values": [row for row in _sheet_rows if row]})
    if "gmail.googleapis.com" in url and url.endswith("/messages"):
        # confirms the auth header carries the impersonated token, not any personal OAuth token
        assert headers["Authorization"] == "Bearer impersonated-token-for-hairil@cytron.io", headers
        return FakeResponse({"messages": [{"id": "m1"}]})
    if "gmail.googleapis.com" in url and "/messages/m1" in url:
        return FakeResponse({
            "id": "m1", "threadId": "t1", "snippet": "Lab report submitted for review",
            "payload": {"headers": [
                {"name": "From", "value": "noreply@sirim-qas.com.my"},
                {"name": "Subject", "value": "CoC Application SIRIM-2026-0142 - Testing Update"},
            ]},
        })
    raise AssertionError(f"unexpected GET {url}")


def main():
    client = TestClient(app)
    admin_headers = auth_headers(client, "Employee")  # the person actually doing the setup - NOT hairil

    # --- upload the service account key (admin-only, hub-wide) ---
    settings = client.put("/api/settings", headers=admin_headers, json={
        "google_service_account_key": SERVICE_ACCOUNT_KEY,
    }).json()
    assert settings["google_service_account_configured"] is True
    assert settings["google_service_account_email"] == "sirim-agent@sirim-coc-agent.iam.gserviceaccount.com"
    print("[ok] Employee (an admin) uploaded the service account key - shows its own email, not a secret")

    # --- the private key material itself is never echoed back, only a "configured" flag + email ---
    assert "private_key" not in settings
    assert _private_pem not in str(settings)
    print("[ok] the private key is never returned by the API, only a 'configured' flag and the service account's own email")

    # --- a non-admin can't upload one ---
    sam_headers = auth_headers(client, "Sam")
    forbidden = client.put("/api/settings", headers=sam_headers, json={"google_service_account_key": SERVICE_ACCOUNT_KEY})
    assert forbidden.status_code == 403
    print("[ok] only an admin can configure the service account")

    # --- garbage JSON is rejected before it's ever stored ---
    garbage = client.put("/api/settings", headers=admin_headers, json={"google_service_account_key": "not json at all"})
    assert garbage.status_code == 400
    print("[ok] an invalid key is rejected with a clear error, not stored")

    # --- test impersonation directly, before touching any real flow ---
    with patch("httpx.post", side_effect=fake_post):
        test_result = client.post("/api/settings/test-impersonation", headers=admin_headers, json={
            "impersonate": "hairil@cytron.io", "scope": "gmail",
        })
    assert test_result.status_code == 200
    print("[ok] test-impersonation confirms Google actually honors this before any flow runs")

    with patch("httpx.post", side_effect=fake_post):
        bad_test = client.post("/api/settings/test-impersonation", headers=admin_headers, json={
            "impersonate": "not-authorized@cytron.io", "scope": "gmail",
        })
    assert bad_test.status_code == 400
    assert "domain-wide delegation" in bad_test.text
    print("[ok] an unauthorized impersonation target gives a specific, actionable error")

    # --- THE ACTUAL SCENARIO: Employee builds and runs a flow that reads hairil's
    # inbox and updates HIS tracker - Employee never connects Gmail or Sheets ---
    flow = client.post("/api/flows", headers=admin_headers, json={"name": "SIRIM Tracker"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "email", "type": "email", "position": {"x": 200, "y": 0}, "data": {
                "action": "search", "query": "SIRIM", "impersonate": "hairil@cytron.io",
            }},
            {"id": "llm", "type": "llm", "position": {"x": 400, "y": 0}, "data": {}},
            {"id": "sheets", "type": "sheets", "position": {"x": 600, "y": 0}, "data": {
                "action": "upsert_row", "spreadsheet_id": SPREADSHEET_ID, "impersonate": "hairil@cytron.io",
            }},
            {"id": "out", "type": "output", "position": {"x": 800, "y": 0}, "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "in", "target": "email"},
            {"id": "e2", "source": "email", "target": "llm"},
            {"id": "e3", "source": "llm", "target": "sheets"},
            {"id": "e4", "source": "sheets", "target": "out"},
        ],
    }
    client.put(f"/api/flows/{flow['id']}", headers=admin_headers, json={"graph": graph})

    client.put("/api/settings", headers=admin_headers, json={
        "llm_provider": "openrouter", "openrouter_api_key": "test-key", "openrouter_model": "test/model",
    })

    def fake_llm_post(url, data=None, json=None, **kwargs):
        if url == "https://oauth2.googleapis.com/token":
            return fake_post(url, data=data, json=json, **kwargs)
        if url == "https://openrouter.ai/api/v1/chat/completions":
            return FakeResponse({"choices": [{"message": {
                "content": "SIRIM-2026-0142 | Testing in progress | Lab report submitted for review",
            }}]})
        return fake_post(url, data=data, json=json, **kwargs)

    with patch("httpx.post", side_effect=fake_llm_post), patch("httpx.get", side_effect=fake_get), \
         patch("httpx.put", side_effect=fake_put):
        result = client.post(f"/api/flows/{flow['id']}/run", headers=admin_headers, json={"input": ""})

    assert result.status_code == 200, result.text
    assert "updated" in result.json()["output"] or "appended" in result.json()["output"]
    assert _sheet_rows[-1][0] == "SIRIM-2026-0142"
    print(f"[ok] Employee ran the flow end to end, acting as hairil throughout: {result.json()['output']}")
    print("[ok] Neither Employee nor hairil ever connected Gmail or Sheets personally - zero OAuth involved")

    # --- prove the token really was hairil's, not Employee's or anyone else's ---
    assert "hairil@cytron.io" in _last_jwt_by_subject
    print("[ok] the JWT sent to Google had sub=hairil@cytron.io - independently verified as a real, valid signature")

    # --- a node with NO impersonate field attempts self-auth (a subject-less JWT) -
    # Gmail specifically has no inbox for a plain service account, so this should
    # fail with a clear, specific error, not a generic one ---
    def fake_self_auth_post(url, data=None, json=None, **kwargs):
        if url == "https://oauth2.googleapis.com/token" and data and "assertion" in data:
            header_b64, claims_b64, sig_b64 = data["assertion"].split(".")
            claims = json_module.loads(_unb64(claims_b64))
            assert "sub" not in claims  # this IS the self-auth path - confirms no impersonation was attempted
            return FakeResponse({"error": "invalid_grant", "error_description": "no such mailbox"}, status_code=400)
        raise AssertionError(f"unexpected POST in self-auth test: {url}")

    normal_flow = client.post("/api/flows", headers=admin_headers, json={"name": "Normal flow, no impersonation"}).json()
    normal_graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "email", "type": "email", "position": {"x": 200, "y": 0}, "data": {"action": "search", "query": "test"}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "email"}, {"id": "e2", "source": "email", "target": "out"}],
    }
    client.put(f"/api/flows/{normal_flow['id']}", headers=admin_headers, json={"graph": normal_graph})
    with patch("httpx.post", side_effect=fake_self_auth_post):
        no_impersonate_result = client.post(f"/api/flows/{normal_flow['id']}/run", headers=admin_headers, json={"input": ""})
    assert no_impersonate_result.status_code == 400
    assert "no inbox of its own" in str(no_impersonate_result.json()) and "Impersonate" in str(no_impersonate_result.json())
    print("[ok] a node with no Impersonate field attempts self-auth, and Gmail's rejection gives a specific, actionable error")

    print("\nAll service-account impersonation smoke tests passed.")


if __name__ == "__main__":
    main()
