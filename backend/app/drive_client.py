"""
Thin wrapper around the Drive REST API v3 - list, read, create, and update
files. Plain httpx, no google-api-python-client, same reasoning as
service_account_auth.py.

Authenticates entirely through the hub-wide Google service account.
`impersonate` left blank means these calls act as the service account's
own identity - files it creates land in its own Drive space, and it can
see/read anything explicitly shared with its own email address (exactly
like sharing a folder with a colleague). Setting `impersonate` instead
makes it act as that Workspace person (needs domain-wide delegation
authorized for the Drive scope).

One wrinkle Drive has that Gmail doesn't: Google Docs/Sheets/Slides
aren't downloadable as raw bytes - they only exist as Google's internal
format and have to be *exported* to a normal file type (text/plain, csv,
etc.) first. Regular uploaded files (PDFs, images, plain text someone
dragged in) don't need that step. _download logic branches on mimeType
to handle both.
"""
import httpx

from . import hub_settings, service_account_auth

API_BASE = "https://www.googleapis.com/drive/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"

SCOPES = ["https://www.googleapis.com/auth/drive"]

# Google Workspace's internal formats can't be downloaded directly - each maps
# to a plain export format we can actually read/embed.
_EXPORT_MIME_MAP = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",  # exports only the first sheet
    "application/vnd.google-apps.presentation": "text/plain",
}

FIELDS = "id,name,mimeType,modifiedTime,size,webViewLink,parents"


class DriveError(Exception):
    pass


def _headers(impersonate: str | None = None, access_token: str | None = None) -> dict:
    """access_token, when given, is a resolved per-user OAuth token (Path B),
    used directly, bypassing the service account entirely. Unset is the
    default, unchanged path: the hub-wide service account."""
    if access_token:
        return {"Authorization": f"Bearer {access_token}"}
    key_info = hub_settings.get_service_account_key()
    if key_info is None:
        raise DriveError("Drive isn't configured yet - add a Google service account key on the Settings page")
    try:
        token = service_account_auth.get_access_token(key_info, SCOPES, impersonate)
    except service_account_auth.ServiceAccountError as exc:
        raise DriveError(str(exc)) from exc
    return {"Authorization": f"Bearer {token}"}


def _handle_error(resp: httpx.Response, impersonate: str | None, context: str) -> None:
    if resp.status_code < 400:
        return
    try:
        detail = resp.json().get("error", {}).get("message", resp.text)
    except ValueError:
        detail = resp.text
    if not impersonate:
        raise DriveError(
            f"Drive rejected this ({context}: \"{detail}\"). Acting as the service account's own "
            f"identity only sees files explicitly shared with its email address - make sure the "
            f"file/folder is actually shared with it, or set this node's 'Impersonate' field to act "
            f"as a specific Workspace person instead."
        )
    raise DriveError(f"Drive rejected this ({context} as '{impersonate}'): {detail}")


def list_files(search: str = "", max_results: int = 20, *, impersonate: str | None = None,
                access_token: str | None = None) -> list[dict]:
    query = "trashed = false"
    if search:
        escaped = search.replace("'", "\\'")
        query = f"name contains '{escaped}' and trashed = false"
    resp = httpx.get(
        f"{API_BASE}/files",
        headers=_headers(impersonate, access_token),
        params={"q": query, "pageSize": max_results, "fields": f"files({FIELDS})"},
        timeout=30,
    )
    _handle_error(resp, impersonate, "listing files")
    return resp.json().get("files", [])


def get_file_metadata(file_id: str, *, impersonate: str | None = None, access_token: str | None = None) -> dict:
    resp = httpx.get(
        f"{API_BASE}/files/{file_id}",
        headers=_headers(impersonate, access_token),
        params={"fields": FIELDS},
        timeout=30,
    )
    _handle_error(resp, impersonate, "reading file metadata")
    return resp.json()


def read_file_content(file_id: str, *, impersonate: str | None = None, access_token: str | None = None) -> dict:
    """Returns {"name", "mime_type", "content"} with content always as text -
    good enough for feeding into a prompt or a RAG ingestion step. Binary
    files (images, etc.) aren't meaningfully "read" this way; this is aimed
    at docs, sheets, and plain text/CSV files."""
    meta = get_file_metadata(file_id, impersonate=impersonate, access_token=access_token)
    mime_type = meta["mimeType"]

    if mime_type in _EXPORT_MIME_MAP:
        export_mime = _EXPORT_MIME_MAP[mime_type]
        resp = httpx.get(
            f"{API_BASE}/files/{file_id}/export",
            headers=_headers(impersonate, access_token),
            params={"mimeType": export_mime},
            timeout=30,
        )
    else:
        resp = httpx.get(
            f"{API_BASE}/files/{file_id}",
            headers=_headers(impersonate, access_token),
            params={"alt": "media"},
            timeout=30,
        )
    _handle_error(resp, impersonate, "reading file content")
    return {"name": meta["name"], "mime_type": mime_type, "content": resp.text}


def create_file(name: str, content: str, mime_type: str = "text/plain",
                 folder_id: str | None = None, *, impersonate: str | None = None,
                 access_token: str | None = None) -> dict:
    """Two calls rather than one hand-built multipart/related body: create the
    metadata first, then PATCH the content in. Slightly more traffic, a lot
    more readable than constructing Drive's multipart upload format by hand."""
    metadata = {"name": name, "mimeType": mime_type}
    if folder_id:
        metadata["parents"] = [folder_id]

    create_resp = httpx.post(
        f"{API_BASE}/files",
        headers={**_headers(impersonate, access_token), "Content-Type": "application/json"},
        json=metadata,
        params={"fields": FIELDS},
        timeout=30,
    )
    _handle_error(create_resp, impersonate, "creating a file")
    file_id = create_resp.json()["id"]

    return update_file_content(file_id, content, mime_type=mime_type, impersonate=impersonate, access_token=access_token)


def update_file_content(file_id: str, content: str, mime_type: str = "text/plain",
                         *, impersonate: str | None = None, access_token: str | None = None) -> dict:
    resp = httpx.patch(
        f"{UPLOAD_BASE}/files/{file_id}",
        headers={**_headers(impersonate, access_token), "Content-Type": mime_type},
        params={"uploadType": "media", "fields": FIELDS},
        content=content.encode(),
        timeout=30,
    )
    _handle_error(resp, impersonate, "updating file content")
    return resp.json()
