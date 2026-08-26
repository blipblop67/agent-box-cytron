"""
Thin wrapper around the Google Sheets API v4. The operation that actually
matters for a progress-tracker agent is upsert_row: find the row whose
first column matches a key (an application ID, a ticket number, whatever
identifies "the thing being tracked"), and update that row in place - or
append a new one if it's the first time that key's been seen. This is
what "the agent edits the spreadsheet it created" means in practice: not
regenerating the whole file, just updating one row, the same way a person
would.

Every function takes an optional `impersonate` email: when set (and a
Workspace service account is configured hub-wide), the call acts as that
Workspace user via domain-wide delegation instead of the calling user_id's
personal OAuth connection - a spreadsheet created this way lands in that
impersonated user's Drive, the same as if they'd connected Sheets
themselves and run the flow.
"""
import httpx

from . import hub_settings, service_account_auth, sheets_tokens

API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"

IMPERSONATION_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsError(Exception):
    pass


def _headers(user_id: str, impersonate: str | None = None) -> dict:
    if impersonate:
        key_info = hub_settings.get_service_account_key()
        if key_info is None:
            raise SheetsError(
                "This node is set to act as a specific person, but no Google service account is "
                "configured on the Settings page yet."
            )
        try:
            token = service_account_auth.get_access_token_for(key_info, impersonate, IMPERSONATION_SCOPES)
        except service_account_auth.ServiceAccountError as exc:
            raise SheetsError(str(exc)) from exc
    else:
        token = sheets_tokens.get_valid_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def _handle_error(resp: httpx.Response, context: str) -> None:
    if resp.status_code == 404:
        raise SheetsError(f"Spreadsheet not found - check the spreadsheet ID and that it's been shared with this account ({context})")
    if resp.status_code in (401, 403):
        raise SheetsError(f"Access to this spreadsheet was denied - reconnect Sheets on the Connections page ({context})")
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise SheetsError(f"Sheets request failed ({context}): {exc}") from exc


def create_spreadsheet(user_id: str, title: str, headers: list[str] | None = None, sheet_name: str = "Sheet1",
                        *, impersonate: str | None = None) -> dict:
    resp = httpx.post(
        API_BASE,
        headers=_headers(user_id, impersonate),
        json={"properties": {"title": title}, "sheets": [{"properties": {"title": sheet_name}}]},
        timeout=30,
    )
    _handle_error(resp, "create")
    data = resp.json()
    spreadsheet_id = data["spreadsheetId"]

    if headers:
        update_row_at(user_id, spreadsheet_id, sheet_name, row_number=1, values=headers, impersonate=impersonate)

    return {
        "spreadsheet_id": spreadsheet_id,
        "title": title,
        "url": data.get("spreadsheetUrl", f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"),
    }


def read_rows(user_id: str, spreadsheet_id: str, sheet_name: str = "Sheet1", *, impersonate: str | None = None) -> list[list[str]]:
    resp = httpx.get(f"{API_BASE}/{spreadsheet_id}/values/{sheet_name}", headers=_headers(user_id, impersonate), timeout=30)
    _handle_error(resp, "read")
    return resp.json().get("values", [])


def update_row_at(user_id: str, spreadsheet_id: str, sheet_name: str, row_number: int, values: list[str],
                   *, impersonate: str | None = None) -> None:
    """row_number is 1-indexed, matching how a person would talk about "row 3"."""
    end_col = chr(ord("A") + len(values) - 1) if len(values) <= 26 else "Z"
    range_ = f"{sheet_name}!A{row_number}:{end_col}{row_number}"
    resp = httpx.put(
        f"{API_BASE}/{spreadsheet_id}/values/{range_}",
        headers=_headers(user_id, impersonate),
        params={"valueInputOption": "USER_ENTERED"},
        json={"values": [values]},
        timeout=30,
    )
    _handle_error(resp, "update")


def append_row(user_id: str, spreadsheet_id: str, sheet_name: str, values: list[str],
                *, impersonate: str | None = None) -> None:
    resp = httpx.post(
        f"{API_BASE}/{spreadsheet_id}/values/{sheet_name}!A:Z:append",
        headers=_headers(user_id, impersonate),
        params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
        json={"values": [values]},
        timeout=30,
    )
    _handle_error(resp, "append")


def upsert_row(user_id: str, spreadsheet_id: str, sheet_name: str, values: list[str],
                *, impersonate: str | None = None) -> dict:
    """values[0] is the key - if a row already has that value in column A,
    that row is updated in place; otherwise a new row is appended. This is
    the whole point: calling this repeatedly with the same key keeps
    updating the same row, the way a real progress tracker works."""
    if not values:
        raise SheetsError("Nothing to write - no values given")
    key = values[0]
    existing_rows = read_rows(user_id, spreadsheet_id, sheet_name, impersonate=impersonate)

    for i, row in enumerate(existing_rows):
        if row and row[0] == key:
            row_number = i + 1  # 1-indexed
            update_row_at(user_id, spreadsheet_id, sheet_name, row_number, values, impersonate=impersonate)
            return {"action": "updated", "row": row_number, "key": key}

    append_row(user_id, spreadsheet_id, sheet_name, values, impersonate=impersonate)
    return {"action": "appended", "row": len(existing_rows) + 1, "key": key}
