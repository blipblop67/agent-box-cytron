"""
Exercises the Sheets integration end to end, with the upsert behavior as
the centerpiece - that's the actual feature this exists for ("the agent
edits the spreadsheet it created" rather than only ever appending or
overwriting the whole file). Mocks only Google's HTTP APIs.
Run with: python3 tests/test_sheets.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-sheets-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()

SPREADSHEET_ID = "fake-spreadsheet-id-123"

# simulates the actual state of a Google Sheet across calls in this test
_sheet_rows: list[list[str]] = []


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def fake_post(url, json=None, params=None, headers=None, **kwargs):
    if url == "https://oauth2.googleapis.com/token":
        return FakeResponse({"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600})
    if url == "https://sheets.googleapis.com/v4/spreadsheets":
        return FakeResponse({
            "spreadsheetId": SPREADSHEET_ID,
            "spreadsheetUrl": f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}",
        })
    if url.endswith(":append"):
        _sheet_rows.append(json["values"][0])
        return FakeResponse({})
    raise AssertionError(f"unexpected POST {url}")


def fake_put(url, json=None, params=None, headers=None, **kwargs):
    # e.g. .../values/Sheet1!A3:C3
    range_part = url.rsplit("/", 1)[-1]
    sheet_and_range = range_part.split("!")[1]
    row_number = int("".join(c for c in sheet_and_range.split(":")[0] if c.isdigit()))
    while len(_sheet_rows) < row_number:
        _sheet_rows.append([])
    _sheet_rows[row_number - 1] = json["values"][0]
    return FakeResponse({})


def fake_get(url, params=None, headers=None, **kwargs):
    if url == "https://www.googleapis.com/oauth2/v3/userinfo":
        return FakeResponse({"email": "priya@example.com"})
    if url == f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/Sheet1":
        return FakeResponse({"values": [row for row in _sheet_rows if row]})
    raise AssertionError(f"unexpected GET {url}")


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Priya")

    status = client.get("/api/sheets/status", headers=headers).json()
    assert status == {"connected": False}
    print("[ok] starts disconnected")

    client.put("/api/settings", headers=headers, json={
        "google_client_id": "test-client-id", "google_client_secret": "test-client-secret",
    })

    start = client.get("/api/sheets/auth/start", headers=headers).json()
    state = start["authorization_url"].split("state=")[1].split("&")[0]
    with patch("httpx.post", side_effect=fake_post), patch("httpx.get", side_effect=fake_get):
        callback = client.get("/api/sheets/auth/callback", params={"code": "fake-code", "state": state}, follow_redirects=False)
    assert callback.status_code in (302, 307)
    print("[ok] OAuth connect flow completed")

    # --- create a tracking spreadsheet with headers ---
    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put):
        created = client.post("/api/sheets/spreadsheets", headers=headers, json={
            "title": "SIRIM CoC Tracker", "headers": ["Application ID", "Status", "Notes"],
        }).json()
    assert created["spreadsheet_id"] == SPREADSHEET_ID
    assert _sheet_rows[0] == ["Application ID", "Status", "Notes"]
    print(f"[ok] created a spreadsheet with a header row: {_sheet_rows[0]}")

    # --- THE ACTUAL POINT: upserting the same key twice updates the SAME row, doesn't duplicate it ---
    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put), \
         patch("httpx.get", side_effect=fake_get):
        first = client.post(f"/api/sheets/spreadsheets/{SPREADSHEET_ID}/upsert-row", headers=headers, json={
            "values": ["SIRIM-2026-001", "Application submitted", "Awaiting document review"],
        }).json()
    assert first["action"] == "appended" and first["row"] == 2
    print(f"[ok] first mention of an application appends a new row: {_sheet_rows[1]}")

    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put), \
         patch("httpx.get", side_effect=fake_get):
        second = client.post(f"/api/sheets/spreadsheets/{SPREADSHEET_ID}/upsert-row", headers=headers, json={
            "values": ["SIRIM-2026-001", "Testing in progress", "Lab report received, awaiting results"],
        }).json()
    assert second["action"] == "updated" and second["row"] == 2  # same row, not a new one
    assert len(_sheet_rows) == 2  # still only 2 rows total (header + the one application) - no duplicate
    assert _sheet_rows[1] == ["SIRIM-2026-001", "Testing in progress", "Lab report received, awaiting results"]
    print(f"[ok] a second update for the SAME application ID updates row 2 in place, not a new row: {_sheet_rows[1]}")

    # --- a different application ID gets its own new row ---
    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put), \
         patch("httpx.get", side_effect=fake_get):
        third = client.post(f"/api/sheets/spreadsheets/{SPREADSHEET_ID}/upsert-row", headers=headers, json={
            "values": ["SIRIM-2026-002", "Application submitted", "New product line"],
        }).json()
    assert third["action"] == "appended" and third["row"] == 3
    assert len(_sheet_rows) == 3
    print(f"[ok] a different application ID gets its own row: {_sheet_rows[2]}")

    # --- reading the sheet back shows all rows ---
    with patch("httpx.get", side_effect=fake_get), patch("httpx.post", side_effect=fake_post):
        read_back = client.get(f"/api/sheets/spreadsheets/{SPREADSHEET_ID}/rows", headers=headers).json()
    assert len(read_back["rows"]) == 3
    print(f"[ok] read back {len(read_back['rows'])} rows total")

    # --- now use it from an actual flow: LLM output (pipe-delimited) -> Sheets upsert_row node ---
    flow = client.post("/api/flows", headers=headers, json={"name": "CoC Tracker Update"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "sheets", "type": "sheets", "position": {"x": 200, "y": 0}, "data": {
                "action": "upsert_row", "spreadsheet_id": SPREADSHEET_ID, "sheet_name": "Sheet1",
            }},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "sheets"}, {"id": "e2", "source": "sheets", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})
    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put), \
         patch("httpx.get", side_effect=fake_get):
        flow_result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={
            "input": "SIRIM-2026-001 | Certificate issued | Approved, certificate sent to applicant",
        })
    assert flow_result.status_code == 200, flow_result.text
    assert "updated" in flow_result.json()["output"]
    assert _sheet_rows[1][1] == "Certificate issued"
    print(f"[ok] a real flow updated the tracker via a Sheets node: {flow_result.json()['output']}")

    # --- a single run can update MULTIPLE applications at once (one email check often touches several) ---
    with patch("httpx.post", side_effect=fake_post), patch("httpx.put", side_effect=fake_put), \
         patch("httpx.get", side_effect=fake_get):
        multi_result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={
            "input": (
                "SIRIM-2026-002 | Testing in progress | Lab report submitted\n"
                "SIRIM-2026-003 | Application submitted | New application received"
            ),
        })
    assert multi_result.status_code == 200, multi_result.text
    assert len(_sheet_rows) == 4  # header + 3 distinct applications now
    assert _sheet_rows[2][1] == "Testing in progress"  # SIRIM-2026-002 updated in place, still row 3
    assert _sheet_rows[3][0] == "SIRIM-2026-003"  # a brand new application, its own new row
    print(f"[ok] a single run updated two different applications at once: {multi_result.json()['output']}")

    # --- "nothing to update" is a graceful no-op, not an error - important for a scheduled tracker
    # that will often run and genuinely find nothing new ---
    none_result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": "NONE"})
    assert none_result.status_code == 200
    assert none_result.json()["output"] == "(nothing to update)"
    assert len(_sheet_rows) == 4  # unchanged - nothing was written
    print("[ok] a 'NONE' response from the LLM is a graceful no-op, not a failed run")

    # --- a missing spreadsheet ID gives a clear error, not a raw exception ---
    broken_flow = client.post("/api/flows", headers=headers, json={"name": "Broken sheets node"}).json()
    broken_graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "sheets", "type": "sheets", "position": {"x": 200, "y": 0}, "data": {"action": "read"}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "sheets"}, {"id": "e2", "source": "sheets", "target": "out"}],
    }
    client.put(f"/api/flows/{broken_flow['id']}", headers=headers, json={"graph": broken_graph})
    broken_result = client.post(f"/api/flows/{broken_flow['id']}/run", headers=headers, json={"input": ""})
    assert broken_result.status_code == 400
    assert "spreadsheet ID" in str(broken_result.json())
    print("[ok] a Sheets node with no spreadsheet ID gives a clear error")

    # --- disconnect ---
    client.delete("/api/sheets/auth", headers=headers)
    assert client.get("/api/sheets/status", headers=headers).json() == {"connected": False}
    print("[ok] disconnect works")

    print("\nAll Sheets smoke tests passed.")


if __name__ == "__main__":
    main()
