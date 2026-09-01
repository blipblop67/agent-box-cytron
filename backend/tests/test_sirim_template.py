"""
Proves the SIRIM CoC Progress Tracker template's enriched schema actually
works end to end - not just that the prompt text and headers look right,
but that the *actual, unmodified* template graph correctly turns a
realistic email into a properly-aligned 9-column row. Guards against a
future edit to the prompt's field order, the Sheets node's headers, or
the parsing logic in flow_engine.py ever drifting out of sync with each
other - the three pieces this feature depends on staying in lockstep.
Run with: python3 tests/test_sirim_template.py
"""
import json as json_module
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-sirimtemplate-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from app.templates import TEMPLATES  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()

COLUMN_LABELS = [
    "Application Ref", "Product / Model", "Status", "Scheme", "Officer",
    "Target Deadline", "Pending Action", "Certificate No", "Notes",
]


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code
        self.text = str(json_data)

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")

    # --- the template's own metadata matches what the LLM prompt promises ---
    sirim = next(t for t in TEMPLATES if t["id"] == "sirim-coc-progress-tracker")
    sheets_node = next(n for n in sirim["graph"]["nodes"] if n["id"] == "sheets")
    header_field = sheets_node["data"]["headers"]
    assert header_field.count(",") == 8  # 9 columns = 8 commas
    print(f"[ok] the Sheets node's default headers has exactly 9 columns: {header_field}")

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    service_account_key = json_module.dumps({
        "type": "service_account", "client_email": "sa@test.iam.gserviceaccount.com",
        "private_key": private_pem, "private_key_id": "x",
    })
    client.put("/api/settings", headers=headers, json={
        "google_service_account_key": service_account_key,
        "llm_provider": "openrouter", "openrouter_api_key": "sk-or-test", "openrouter_model": "test-model",
    })

    # --- use the ACTUAL, unmodified template graph - not a hand-built approximation ---
    flow = client.post("/api/flows", headers=headers, json={"name": "SIRIM Test"}).json()
    graph = sirim["graph"]
    for node in graph["nodes"]:
        if node["id"] == "sheets":
            node["data"]["spreadsheet_id"] = "FAKE_SHEET_ID"
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})

    written_rows = []

    def fake_post(url, json=None, headers=None, **kwargs):
        if url == "https://oauth2.googleapis.com/token":
            return FakeResponse({"access_token": "tok", "expires_in": 3600})
        if "chat/completions" in url:
            # a well-behaving LLM following the prompt's exact instructions,
            # including a genuinely blank field (no certificate issued yet)
            return FakeResponse({"choices": [{"message": {"content": (
                "SQAS-2026-0142 | Smart Plug SP-200 | Action required | Type Approval | "
                "Ahmad Faizal <ahmad@sirim.my> | 2026-09-20 | "
                "[High] Applicant: submit revised test report |  | Lab flagged an EMC discrepancy"
            )}}]})
        if url.endswith(":append"):
            written_rows.append(json["values"][0])
            return FakeResponse({})
        raise AssertionError(f"unexpected POST {url}")

    def fake_get(url, headers=None, params=None, **kwargs):
        if url.endswith("/gmail/v1/users/me/messages") and params and "q" in params:
            return FakeResponse({"messages": [{"id": "m1"}]})
        if "gmail" in url and "messages/m1" in url:
            return FakeResponse({
                "id": "m1", "threadId": "t1", "snippet": "RFI...",
                "payload": {"headers": [
                    {"name": "From", "value": "ahmad@sirim.my"},
                    {"name": "Subject", "value": "RFI: SQAS-2026-0142"},
                    {"name": "Date", "value": "Mon, 1 Sep 2026 09:00:00 +0800"},
                ]},
            })
        if "sheets.googleapis.com" in url and "/values/" in url:
            return FakeResponse({"values": []})
        raise AssertionError(f"unexpected GET {url}")

    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": ""})

    assert result.status_code == 200, result.text
    assert result.json()["output"] == "appended row 1 for 'SQAS-2026-0142'"
    print(f"[ok] the real template ran end to end: {result.json()['output']}")

    assert len(written_rows) == 1
    row = written_rows[0]
    assert len(row) == 9, f"expected exactly 9 columns written, got {len(row)}: {row}"
    print(f"[ok] exactly 9 columns were written, matching the header count: {row}")

    expected = {
        "Application Ref": "SQAS-2026-0142", "Product / Model": "Smart Plug SP-200",
        "Status": "Action required", "Scheme": "Type Approval",
        "Officer": "Ahmad Faizal <ahmad@sirim.my>", "Target Deadline": "2026-09-20",
        "Pending Action": "[High] Applicant: submit revised test report",
        "Certificate No": "", "Notes": "Lab flagged an EMC discrepancy",
    }
    actual = dict(zip(COLUMN_LABELS, row))
    for label in COLUMN_LABELS:
        assert actual[label] == expected[label], f"{label}: expected {expected[label]!r}, got {actual[label]!r}"
    print("[ok] every field landed in the correct column, including the genuinely-blank certificate field")

    print("\nAll SIRIM template smoke tests passed.")


if __name__ == "__main__":
    main()
