"""
Direct Sheets action endpoints - create a spreadsheet, read it, or upsert
a row - for manual use and testing. A flow's Sheets node goes through
flow_engine.py directly rather than these; this router is a plain API
surface over sheets_client.py, which does the actual work (including the
upsert-by-key logic that makes a real progress tracker possible).

There's no per-user "connect" step anymore - Sheets authenticates
entirely through the hub-wide Google service account (see
service_account_auth.py and hub_settings.py). `impersonate` (a Workspace
email) is optional - left blank, everything happens in the service
account's own Drive space.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import sheets_client
from .auth import get_current_user

router = APIRouter(prefix="/sheets", tags=["sheets"])


class CreateSpreadsheetRequest(BaseModel):
    title: str
    headers: list[str] | None = None
    sheet_name: str = "Sheet1"
    impersonate: str | None = None


@router.post("/spreadsheets")
def create_spreadsheet(body: CreateSpreadsheetRequest, user: dict = Depends(get_current_user)):
    try:
        return sheets_client.create_spreadsheet(body.title, body.headers, body.sheet_name, impersonate=body.impersonate)
    except sheets_client.SheetsError as exc:
        raise HTTPException(400, str(exc))


@router.get("/spreadsheets/{spreadsheet_id}/rows")
def read_rows(spreadsheet_id: str, sheet_name: str = "Sheet1", impersonate: str | None = None,
              user: dict = Depends(get_current_user)):
    try:
        return {"rows": sheets_client.read_rows(spreadsheet_id, sheet_name, impersonate=impersonate)}
    except sheets_client.SheetsError as exc:
        raise HTTPException(400, str(exc))


class UpsertRowRequest(BaseModel):
    sheet_name: str = "Sheet1"
    values: list[str]
    impersonate: str | None = None


@router.post("/spreadsheets/{spreadsheet_id}/upsert-row")
def upsert_row(spreadsheet_id: str, body: UpsertRowRequest, user: dict = Depends(get_current_user)):
    try:
        return sheets_client.upsert_row(spreadsheet_id, body.sheet_name, body.values, impersonate=body.impersonate)
    except sheets_client.SheetsError as exc:
        raise HTTPException(400, str(exc))
