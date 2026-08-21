"""
Exercises the whole Drive integration - connect, list, read (both a plain
file and a native Google Doc export), create, update - without touching real
Google servers. Run with: python3 tests/test_drive.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-drive-test-"))
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GOOGLE_DRIVE_REDIRECT_URI", "http://localhost:8811/api/drive/auth/callback")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()

FILES = {
    "doc-1": {  # a native Google Doc - needs /export, not /files/{id}?alt=media
        "id": "doc-1", "name": "Q3 Plan", "mimeType": "application/vnd.google-apps.document",
        "modifiedTime": "2026-07-01T00:00:00Z", "webViewLink": "https://docs.google.com/doc-1",
    },
    "plain-1": {  # a regular uploaded text file - downloads directly via alt=media
        "id": "plain-1", "name": "notes.txt", "mimeType": "text/plain",
        "modifiedTime": "2026-07-02T00:00:00Z", "webViewLink": "https://drive.google.com/plain-1",
    },
}
EXPORTS = {"doc-1": "Q3 priorities: ship the RAG pipeline, then Gmail, then Drive."}
DOWNLOADS = {"plain-1": "just some plain notes"}


class FakeResponse:
    def __init__(self, json_data=None, text_data=None, status_code=200):
        self._json = json_data
        self.text = text_data if text_data is not None else ""
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"fake HTTP {self.status_code}: {self._json or self.text}")

    def json(self):
        return self._json


def fake_post(url, data=None, json=None, headers=None, params=None, **kwargs):
    if url == "https://oauth2.googleapis.com/token":
        if data["grant_type"] == "authorization_code":
            assert data["code"] == "fake-drive-code"
            return FakeResponse({"access_token": "at-1", "refresh_token": "rt-drive-1", "expires_in": 3600})
        if data["grant_type"] == "refresh_token":
            assert data["refresh_token"] == "rt-drive-1"
            return FakeResponse({"access_token": "at-fresh", "expires_in": 3600})
    if url == "https://www.googleapis.com/drive/v3/files" and json is not None:
        # file creation (metadata step)
        new_id = "created-1"
        FILES[new_id] = {"id": new_id, "name": json["name"], "mimeType": json["mimeType"],
                          "modifiedTime": "2026-07-28T00:00:00Z", "webViewLink": f"https://drive.google.com/{new_id}"}
        return FakeResponse(FILES[new_id])
    raise AssertionError(f"unexpected POST {url} data={data} json={json}")


def fake_patch(url, headers=None, params=None, content=None, **kwargs):
    assert url.startswith("https://www.googleapis.com/upload/drive/v3/files/")
    file_id = url.rsplit("/", 1)[-1]
    DOWNLOADS[file_id] = content.decode()
    return FakeResponse(FILES[file_id])


def fake_get(url, headers=None, params=None, **kwargs):
    if url == "https://www.googleapis.com/oauth2/v3/userinfo":
        assert headers["Authorization"] == "Bearer at-1"
        return FakeResponse({"email": "priya@example.com"})

    if url == "https://www.googleapis.com/drive/v3/files" and "q" in (params or {}):
        assert "trashed = false" in params["q"]
        return FakeResponse({"files": list(FILES.values())})

    if url.startswith("https://www.googleapis.com/drive/v3/files/") and url.endswith("/export"):
        file_id = url.split("/files/")[1].split("/export")[0]
        return FakeResponse(text_data=EXPORTS[file_id])

    if url.startswith("https://www.googleapis.com/drive/v3/files/") and params.get("alt") == "media":
        file_id = url.rsplit("/", 1)[-1]
        return FakeResponse(text_data=DOWNLOADS[file_id])

    if url.startswith("https://www.googleapis.com/drive/v3/files/"):
        file_id = url.rsplit("/", 1)[-1]
        return FakeResponse(FILES[file_id])

    raise AssertionError(f"unexpected GET {url} params={params}")


def main():
    with patch("httpx.post", side_effect=fake_post), \
         patch("httpx.get", side_effect=fake_get), \
         patch("httpx.patch", side_effect=fake_patch):
        client = TestClient(app)
        headers = auth_headers(client, "Priya")

        assert client.get("/api/drive/status", headers=headers).json() == {"connected": False}
        print("[ok] starts disconnected")

        start = client.get("/api/drive/auth/start", headers=headers).json()
        assert "drive.readonly" in start["authorization_url"]
        assert "drive.file" in start["authorization_url"]
        state = start["authorization_url"].split("state=")[1].split("&")[0]
        print("[ok] auth/start requested readonly + file scopes")

        callback = client.get(
            "/api/drive/auth/callback",
            params={"code": "fake-drive-code", "state": state},
            follow_redirects=False,
        )
        assert callback.status_code in (302, 307), callback.status_code

        status = client.get("/api/drive/status", headers=headers).json()
        assert status["connected"] and status["account_email"] == "priya@example.com"
        print(f"[ok] connected as {status['account_email']}")

        files = client.get("/api/drive/files", headers=headers).json()
        assert {f["id"] for f in files} == {"doc-1", "plain-1"}
        print(f"[ok] listed {len(files)} files")

        doc_content = client.get("/api/drive/files/doc-1/content", headers=headers).json()
        assert doc_content["content"] == EXPORTS["doc-1"]
        print(f"[ok] read native Google Doc via export: \"{doc_content['content'][:40]}...\"")

        plain_content = client.get("/api/drive/files/plain-1/content", headers=headers).json()
        assert plain_content["content"] == DOWNLOADS["plain-1"]
        print(f"[ok] read plain file via direct download: \"{plain_content['content']}\"")

        created = client.post(
            "/api/drive/files", headers=headers,
            json={"name": "agent-output.txt", "content": "hello from the hub", "mime_type": "text/plain"},
        ).json()
        assert created["name"] == "agent-output.txt"
        assert DOWNLOADS[created["id"]] == "hello from the hub"
        print(f"[ok] created a new file: {created['id']}")

        updated = client.put(
            f"/api/drive/files/{created['id']}/content", headers=headers,
            json={"content": "updated content", "mime_type": "text/plain"},
        ).json()
        assert updated["id"] == created["id"]
        assert DOWNLOADS[created["id"]] == "updated content"
        print("[ok] updated the file's content")

        client.delete("/api/drive/auth", headers=headers)
        assert client.get("/api/drive/status", headers=headers).json() == {"connected": False}
        print("[ok] disconnect works")

    print("\nAll Drive smoke tests passed.")


if __name__ == "__main__":
    main()
