"""
Thin wrapper around the Google Sheets API v4. The operation that actually
matters for a progress-tracker agent is upsert_row: find the row whose
first column matches a key (an application ID, a ticket number, whatever
identifies "the thing being tracked"), and update that row in place - or
append a new one if it's the first time that key's been seen. This is
what "the agent edits the spreadsheet it created" means in practice: not
regenerating the whole file, just updating one row, the same way a person
would.

Authenticates entirely through the hub-wide Google service account (see
service_account_auth.py) by default. `impersonate` left blank means the
spreadsheet is created in/read from the service account's *own* Drive
space - a completely normal way to use this for a dedicated tracker
nobody else needs personal ownership of. Setting `impersonate` to a
Workspace address instead makes it land in that person's own Drive
(needs domain-wide delegation authorized for the Sheets scope). An
`access_token` (Path B - a resolved per-user OAuth token) bypasses the
service account entirely when a node is configured to act as a specific
person's own Google account instead.
"""
import httpx

from . import hub_settings, service_account_auth

API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsError(Exception):
    pass


def _headers(impersonate: str | None = None, access_token: str | None = None) -> dict:
    if access_token:
        return {"Authorization": f"Bearer {access_token}"}
    key_info = hub_settings.get_service_account_key()
    if key_info is None:
        raise SheetsError("Sheets isn't configured yet - add a Google service account key on the Settings page")
    try:
        token = service_account_auth.get_access_token(key_info, SCOPES, impersonate)
    except service_account_auth.ServiceAccountError as exc:
        raise SheetsError(str(exc)) from exc
    return {"Authorization": f"Bearer {token}"}


def _handle_error(resp: httpx.Response, context: str) -> None:
    if resp.status_code == 404:
        raise SheetsError(f"Spreadsheet not found - check the spreadsheet ID and that it's been shared with this account ({context})")
    if resp.status_code in (401, 403):
        raise SheetsError(f"Access to this spreadsheet was denied - check the service account is configured, and the spreadsheet is shared with it if it wasn't created by it ({context})")
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SheetsError(f"Sheets request failed ({context}): {exc}") from exc


def create_spreadsheet(title: str, headers: list[str] | None = None, sheet_name: str = "Sheet1",
                        *, impersonate: str | None = None, access_token: str | None = None) -> dict:
    resp = httpx.post(
        API_BASE,
        headers=_headers(impersonate, access_token),
        json={"properties": {"title": title}, "sheets": [{"properties": {"title": sheet_name}}]},
        timeout=30,
    )
    _handle_error(resp, "create")
    data = resp.json()
    spreadsheet_id = data["spreadsheetId"]
    sheet_id = data["sheets"][0]["properties"]["sheetId"]

    if headers:
        update_row_at(spreadsheet_id, sheet_name, row_number=1, values=headers, impersonate=impersonate, access_token=access_token)
        _format_header_row(spreadsheet_id, sheet_id, len(headers), impersonate=impersonate, access_token=access_token)

    return {
        "spreadsheet_id": spreadsheet_id,
        "title": title,
        "url": data.get("spreadsheetUrl", f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"),
    }


def _format_header_row(spreadsheet_id: str, sheet_id: int, column_count: int, *, impersonate: str | None = None,
                        access_token: str | None = None) -> None:
    """Bold white text on a dark background, frozen so it stays visible while
    scrolling - the same basic treatment any well-made tracker sheet gets by
    hand, just applied automatically. Purely cosmetic - never raises even if
    it fails, since a plain unstyled header is a fine spreadsheet, just a
    less polished one, and this shouldn't be why a Create action fails."""
    body = {
        "requests": [
            {"updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }},
            {"repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                           "startColumnIndex": 0, "endColumnIndex": column_count},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": {"red": 0.290, "green": 0.208, "blue": 0.125},  # Agent Hub's copper-dim
                    "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True},
                    "verticalAlignment": "MIDDLE",
                    "wrapStrategy": "WRAP",
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment,wrapStrategy)",
            }},
        ],
    }
    try:
        resp = httpx.post(f"{API_BASE}/{spreadsheet_id}:batchUpdate", headers=_headers(impersonate, access_token), json=body, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError:
        pass  # cosmetic only - a flow's Create action should still succeed even if styling fails


def read_rows(spreadsheet_id: str, sheet_name: str = "Sheet1", *, impersonate: str | None = None,
               access_token: str | None = None) -> list[list[str]]:
    resp = httpx.get(f"{API_BASE}/{spreadsheet_id}/values/{sheet_name}", headers=_headers(impersonate, access_token), timeout=30)
    _handle_error(resp, "read")
    return resp.json().get("values", [])


def update_row_at(spreadsheet_id: str, sheet_name: str, row_number: int, values: list[str],
                   *, impersonate: str | None = None, access_token: str | None = None) -> None:
    """row_number is 1-indexed, matching how a person would talk about "row 3"."""
    end_col = chr(ord("A") + len(values) - 1) if len(values) <= 26 else "Z"
    range_ = f"{sheet_name}!A{row_number}:{end_col}{row_number}"
    resp = httpx.put(
        f"{API_BASE}/{spreadsheet_id}/values/{range_}",
        headers=_headers(impersonate, access_token),
        params={"valueInputOption": "USER_ENTERED"},
        json={"values": [values]},
        timeout=30,
    )
    _handle_error(resp, "update")


def append_row(spreadsheet_id: str, sheet_name: str, values: list[str],
                *, impersonate: str | None = None, access_token: str | None = None) -> None:
    resp = httpx.post(
        f"{API_BASE}/{spreadsheet_id}/values/{sheet_name}!A:Z:append",
        headers=_headers(impersonate, access_token),
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json={"values": [values]},
        timeout=30,
    )
    _handle_error(resp, "append")


def upsert_row(spreadsheet_id: str, sheet_name: str, values: list[str],
                *, impersonate: str | None = None, access_token: str | None = None) -> dict:
    """values[0] is the key - if a row already has that value in column A,
    that row is updated in place; otherwise a new row is appended. This is
    the whole point: calling this repeatedly with the same key keeps
    updating the same row, the way a real progress tracker works."""
    if not values:
        raise SheetsError("Nothing to write - no values given")
    key = values[0]
    existing_rows = read_rows(spreadsheet_id, sheet_name, impersonate=impersonate, access_token=access_token)

    for i, row in enumerate(existing_rows):
        if row and row[0] == key:
            row_number = i + 1  # 1-indexed
            update_row_at(spreadsheet_id, sheet_name, row_number, values, impersonate=impersonate, access_token=access_token)
            return {"action": "updated", "row": row_number, "key": key}

    append_row(spreadsheet_id, sheet_name, values, impersonate=impersonate, access_token=access_token)
    return {"action": "appended", "row": len(existing_rows) + 1, "key": key}
