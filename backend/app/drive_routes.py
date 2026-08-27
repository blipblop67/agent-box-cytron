"""
Direct Drive action endpoints - list / read / create / update files - for
manual use, testing, and the Drive node's file picker in the flow editor.
A flow's Drive node goes through flow_engine.py directly rather than
these; this router is a plain API surface over drive_client.py, which
does the actual work.

There's no per-user "connect" step anymore - Drive authenticates entirely
through the hub-wide Google service account (see service_account_auth.py
and hub_settings.py). `impersonate` (a Workspace email) is optional -
left blank, everything happens in the service account's own Drive space.
"""
from fastapi import APIRouter, Depends, HTTPException

from . import drive_client, service_account_auth
from .auth import get_current_user
from .models import DriveFileContent, DriveFileCreate, DriveFileOut, DriveFileUpdate


router = APIRouter(prefix="/drive", tags=["drive"])


@router.get("/files", response_model=list[DriveFileOut])
def list_files(q: str = "", max_results: int = 20, impersonate: str | None = None,
                user: dict = Depends(get_current_user)):
    try:
        return drive_client.list_files(search=q, max_results=max_results, impersonate=impersonate)
    except (ValueError, service_account_auth.ServiceAccountError) as exc:
        raise HTTPException(400, str(exc))


@router.get("/files/{file_id}", response_model=DriveFileOut)
def get_file(file_id: str, impersonate: str | None = None, user: dict = Depends(get_current_user)):
    try:
        return drive_client.get_file_metadata(file_id, impersonate=impersonate)
    except (ValueError, service_account_auth.ServiceAccountError) as exc:
        raise HTTPException(400, str(exc))


@router.get("/files/{file_id}/content", response_model=DriveFileContent)
def read_file(file_id: str, impersonate: str | None = None, user: dict = Depends(get_current_user)):
    try:
        return drive_client.read_file_content(file_id, impersonate=impersonate)
    except (ValueError, service_account_auth.ServiceAccountError) as exc:
        raise HTTPException(400, str(exc))


@router.post("/files", response_model=DriveFileOut)
def create_file(body: DriveFileCreate, user: dict = Depends(get_current_user)):
    try:
        return drive_client.create_file(
            name=body.name, content=body.content, mime_type=body.mime_type,
            folder_id=body.folder_id, impersonate=body.impersonate,
        )
    except (ValueError, service_account_auth.ServiceAccountError) as exc:
        raise HTTPException(400, str(exc))


@router.put("/files/{file_id}/content", response_model=DriveFileOut)
def update_file(file_id: str, body: DriveFileUpdate, user: dict = Depends(get_current_user)):
    try:
        return drive_client.update_file_content(file_id, body.content, mime_type=body.mime_type, impersonate=body.impersonate)
    except (ValueError, service_account_auth.ServiceAccountError) as exc:
        raise HTTPException(400, str(exc))
