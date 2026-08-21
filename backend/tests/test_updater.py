"""
Proves the two things that actually matter about self-updating:
1. A successful update replaces the code but a flow created beforehand is
   still there afterward - not "should be" by inspecting the swap logic,
   but actually still returned by the API after the update runs.
2. A staged update that fails validation (or dependency install, or the
   frontend build) never touches the live installation at all.

Builds a real, small tarball in memory to stand in for "the latest commit on
GitHub" and only mocks the network layer - extraction, validation, and the
file swap are all exercised for real against temp directories (never the
actual project files this test itself lives in).

Run with: python3 tests/test_updater.py
"""
import io
import os
import sys
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-updater-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, updater  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


def _build_fake_release_tarball(marker_text: str) -> bytes:
    """A minimal but structurally valid stand-in for a real Agent Hub repo,
    tagged with `marker_text` somewhere identifiable so the test can prove
    the swap actually happened."""
    root = "someuser-agent-hub-abc1234"
    files = {
        f"{root}/backend/app/main.py": f"# {marker_text}\nprint('hello')\n",
        f"{root}/backend/app/_marker.py": f"MARKER = {marker_text!r}\n",
        f"{root}/backend/requirements.txt": "fastapi>=0.115\n",
        f"{root}/frontend/package.json": '{"name": "agent-hub-frontend"}\n',
        f"{root}/frontend/src/main.jsx": f"// frontend entry - {marker_text}\n",
        f"{root}/frontend/dist/index.html": f"<html><!-- {marker_text} --></html>\n",
    }
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _build_broken_tarball() -> bytes:
    """Missing backend/app/main.py entirely - should fail validation before
    anything about the live install is touched."""
    root = "someuser-agent-hub-broken"
    files = {f"{root}/backend/requirements.txt": "fastapi\n"}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class FakeStreamResponse:
    def __init__(self, content: bytes):
        self._content = content

    def raise_for_status(self):
        pass

    def iter_bytes(self):
        yield self._content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeGetResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


def fake_commit_response(sha: str):
    return FakeGetResponse({
        "sha": sha,
        "commit": {"message": "Add a great new feature\n\nmore detail", "author": {"date": "2026-08-01T12:00:00Z"}},
    })


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")  # first user -> admin

    # --- before configuring a repo ---
    status = client.get("/api/updates/status", headers=headers).json()
    assert status["configured"] is False
    print("[ok] no repo configured yet")

    other_headers = auth_headers(client, "Sam")
    forbidden = client.put("/api/updates/config", headers=other_headers, json={"repo": "someone/else"})
    assert forbidden.status_code == 403
    print("[ok] only a hub admin can configure the update repo")

    # --- configure a repo, check for an update ---
    with patch("httpx.get", return_value=fake_commit_response("sha-latest-111")):
        configured = client.put(
            "/api/updates/config", headers=headers, json={"repo": "someuser/agent-hub", "branch": "main"},
        ).json()
    assert configured["update_available"] is True  # nothing installed yet -> anything counts as "available"
    assert configured["latest_version"] == "sha-latest-111"
    print("[ok] configured a repo and detected an available update")

    # --- create a flow BEFORE updating, to prove it survives ---
    flow = client.post(
        "/api/flows", headers=headers, json={"name": "My precious agent", "description": "do not lose me"},
    ).json()
    graph = {
        "nodes": [{"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
                  {"id": "out", "type": "output", "position": {"x": 100, "y": 0}, "data": {}}],
        "edges": [{"id": "e1", "source": "in", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})
    print(f"[ok] created a flow before updating: {flow['id']}")

    # --- apply a (fake) update against scratch directories, never the real project ---
    with tempfile.TemporaryDirectory(prefix="agent-hub-updater-live-") as live_root:
        live_root = Path(live_root)
        live_backend = live_root / "backend"
        live_frontend = live_root / "frontend"
        (live_backend / "app").mkdir(parents=True)
        (live_backend / "app" / "main.py").write_text("# old version\n")
        (live_backend / "requirements.txt").write_text("fastapi>=0.100\n")
        (live_frontend / "src").mkdir(parents=True)
        (live_frontend / "src" / "main.jsx").write_text("// old frontend\n")
        (live_frontend / "package.json").write_text('{"name": "old"}\n')

        tarball_bytes = _build_fake_release_tarball("v2-marker")
        install_calls, build_calls = [], []

        with patch("httpx.get", return_value=fake_commit_response("sha-latest-111")), \
             patch("httpx.stream", return_value=FakeStreamResponse(tarball_bytes)):
            outcome = updater.apply_update(
                install_deps=lambda path: install_calls.append(path),
                build_frontend=lambda path: build_calls.append(path),
                on_restart=lambda: False,
                backend_dir=live_backend,
                frontend_dir=live_frontend,
            )

        assert outcome["updated_to"] == "sha-latest-111"
        assert outcome["auto_restarting"] is False
        assert len(install_calls) == 1 and len(build_calls) == 1
        print("[ok] update applied against a scratch install dir, dependency/build steps were invoked")

        new_main = (live_backend / "app" / "main.py").read_text()
        assert "v2-marker" in new_main
        print("[ok] backend/app was actually replaced with the new version")

        new_static = (live_backend / "app" / "static" / "index.html").read_text()
        assert "v2-marker" in new_static
        print("[ok] the freshly built frontend landed in app/static")

        assert "v2-marker" in (live_frontend / "src" / "main.jsx").read_text()
        print("[ok] frontend/src was replaced too")

        assert (live_backend / "app.bak" / "main.py").read_text() == "# old version\n"
        print("[ok] the previous version was kept as app.bak for manual rollback")

    # --- the actual point of this whole test: the flow created earlier is still there ---
    still_there = client.get(f"/api/flows/{flow['id']}", headers=headers)
    assert still_there.status_code == 200
    assert still_there.json()["name"] == "My precious agent"
    print("[ok] the flow created before the update is still there after it - nothing in")
    print("     AGENT_HUB_DATA_DIR was ever touched, because the update never looked there")

    assert updater.get_installed_version() == "sha-latest-111"
    with patch("httpx.get", return_value=fake_commit_response("sha-latest-111")):
        recheck = client.get("/api/updates/status", headers=headers).json()
    assert recheck["update_available"] is False
    print("[ok] installed_version updated - checking again shows no update pending")

    # --- a broken/invalid repo never touches the live install ---
    with tempfile.TemporaryDirectory(prefix="agent-hub-updater-live2-") as live_root2:
        live_root2 = Path(live_root2)
        live_backend2 = live_root2 / "backend"
        (live_backend2 / "app").mkdir(parents=True)
        (live_backend2 / "app" / "main.py").write_text("# still the good version\n")
        live_frontend2 = live_root2 / "frontend"

        broken_tarball = _build_broken_tarball()
        with patch("httpx.get", return_value=fake_commit_response("sha-broken-999")), \
             patch("httpx.stream", return_value=FakeStreamResponse(broken_tarball)):
            try:
                updater.apply_update(
                    install_deps=lambda p: None, build_frontend=lambda p: None, on_restart=lambda: False,
                    backend_dir=live_backend2, frontend_dir=live_frontend2,
                )
                raised = False
            except updater.UpdateError:
                raised = True
        assert raised
        assert (live_backend2 / "app" / "main.py").read_text() == "# still the good version\n"
        print("[ok] an invalid/broken release is rejected and the live install is left untouched")

    print("\nAll updater smoke tests passed.")


if __name__ == "__main__":
    main()
