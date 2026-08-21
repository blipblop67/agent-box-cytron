"""
Thin wrapper around the Drive REST API v3 - list, read, create, and update
files. Plain httpx, no google-api-python-client, same reasoning as gmail_client.py.

One wrinkle Drive has that Gmail doesn't: Google Docs/Sheets/Slides aren't
downloadable as raw bytes - they only exist as Google's internal format and
have to be *exported* to a normal file type (text/plain, csv, etc.) first.
Regular uploaded files (PDFs, images, plain text someone dragged in) don't
need that step. _download logic branches on mimeType to handle both.
"""
import httpx

from . import drive_tokens

API_BASE = "https://www.googleapis.com/drive/v3"
UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"

# Google Workspace's internal formats can't be downloaded directly - each maps
# to a plain export format we can actually read/embed.
_EXPORT_MIME_MAP = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",  # exports only the first sheet
    "application/vnd.google-apps.presentation": "text/plain",
}

FIELDS = "id,name,mimeType,modifiedTime,size,webViewLink,parents"


def _headers(user_id: str) -> dict:
    token = drive_tokens.get_valid_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}


def list_files(user_id: str, search: str = "", max_results: int = 20) -> list[dict]:
    query = "trashed = false"
    if search:
        escaped = search.replace("'", "\\'")
        query = f"name contains '{escaped}' and trashed = false"
    resp = httpx.get(
        f"{API_BASE}/files",
        headers=_headers(user_id),
        params={"q": query, "pageSize": max_results, "fields": f"files({FIELDS})"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("files", [])


def get_file_metadata(user_id: str, file_id: str) -> dict:
    resp = httpx.get(
        f"{API_BASE}/files/{file_id}",
        headers=_headers(user_id),
        params={"fields": FIELDS},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def read_file_content(user_id: str, file_id: str) -> dict:
    """Returns {"name", "mime_type", "content"} with content always as text -
    good enough for feeding into a prompt or a RAG ingestion step. Binary
    files (images, etc.) aren't meaningfully "read" this way; this is aimed
    at docs, sheets, and plain text/CSV files."""
    meta = get_file_metadata(user_id, file_id)
    mime_type = meta["mimeType"]

    if mime_type in _EXPORT_MIME_MAP:
        export_mime = _EXPORT_MIME_MAP[mime_type]
        resp = httpx.get(
            f"{API_BASE}/files/{file_id}/export",
            headers=_headers(user_id),
            params={"mimeType": export_mime},
            timeout=30,
        )
    else:
        resp = httpx.get(
            f"{API_BASE}/files/{file_id}",
            headers=_headers(user_id),
            params={"alt": "media"},
            timeout=30,
        )
    resp.raise_for_status()
    return {"name": meta["name"], "mime_type": mime_type, "content": resp.text}


def create_file(user_id: str, name: str, content: str, mime_type: str = "text/plain",
                 folder_id: str | None = None) -> dict:
    """Two calls rather than one hand-built multipart/related body: create the
    metadata first, then PATCH the content in. Slightly more traffic, a lot
    more readable than constructing Drive's multipart upload format by hand."""
    metadata = {"name": name, "mimeType": mime_type}
    if folder_id:
        metadata["parents"] = [folder_id]

    create_resp = httpx.post(
        f"{API_BASE}/files",
        headers={**_headers(user_id), "Content-Type": "application/json"},
        json=metadata,
        params={"fields": FIELDS},
        timeout=30,
    )
    create_resp.raise_for_status()
    file_id = create_resp.json()["id"]

    return update_file_content(user_id, file_id, content, mime_type=mime_type)


def update_file_content(user_id: str, file_id: str, content: str, mime_type: str = "text/plain") -> dict:
    resp = httpx.patch(
        f"{UPLOAD_BASE}/files/{file_id}",
        headers={**_headers(user_id), "Content-Type": mime_type},
        params={"uploadType": "media", "fields": FIELDS},
        content=content.encode(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
