"""
Self-update: check a GitHub repo/branch for a newer commit than what's
currently installed, and if an admin asks for it, download and swap in the
new code.

The safety property this whole module is built around: user data
(flows, knowledge bases, uploaded documents, connections, schedules) lives
in AGENT_HUB_DATA_DIR, which is nowhere near the code directories this
module touches (backend/app, frontend/src). An update physically cannot
reach it - not because the code is careful, but because it never looks
there in the first place.

The other safety property: everything risky (download, extract, validate,
reinstall dependencies, rebuild the frontend) happens in a temp staging
directory first. The live installation is only touched in the final swap
step, which is just a few directory moves - if anything upstream failed,
we never got that far, and the running hub is untouched.
"""
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path

import httpx

from . import db

logger = logging.getLogger(__name__)

# app/updater.py -> app -> backend -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

GITHUB_API = "https://api.github.com"


class UpdateError(Exception):
    pass


# ---- configuration (which repo/branch to track) --------------------------------

# The reference deployment - defaults so a fresh hub is ready to check for
# updates immediately, with nothing to type in. Still fully overridable from
# Settings (e.g. to point at your own fork) - this only applies when nothing
# has been explicitly configured yet.
DEFAULT_UPDATE_REPO = "blipblop67/agent-box-cytron"
DEFAULT_UPDATE_BRANCH = "main"


def get_update_config() -> dict:
    return {
        "repo": db.get_setting("update_repo") or DEFAULT_UPDATE_REPO,
        "branch": db.get_setting("update_branch") or DEFAULT_UPDATE_BRANCH,
    }


def set_update_config(repo: str | None, branch: str | None) -> None:
    if repo is not None:
        db.set_setting("update_repo", repo.strip())
    if branch is not None:
        db.set_setting("update_branch", branch.strip() or "main")


def get_installed_version() -> str:
    return db.get_setting("installed_version") or ""


# ---- checking --------------------------------------------------------------------

def check_for_update() -> dict:
    config = get_update_config()
    if not config["repo"]:
        raise UpdateError("No GitHub repository configured yet")

    try:
        resp = httpx.get(
            f"{GITHUB_API}/repos/{config['repo']}/commits/{config['branch']}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise UpdateError(f"Couldn't reach GitHub to check for updates: {exc}") from exc

    if resp.status_code == 404:
        raise UpdateError(
            f"Couldn't find {config['repo']}@{config['branch']} on GitHub. Either the repo/branch "
            f"name is wrong, or the repository is private - this check is an anonymous request, and "
            f"GitHub returns this same 'not found' error for private repos as for ones that don't "
            f"exist at all, so it can only see public repositories."
        )
    if resp.status_code == 403:
        raise UpdateError(
            "GitHub turned down this check (403) - almost always its anonymous rate limit (60 "
            "requests/hour, shared by everyone checking from this network), not a problem with the "
            "repo itself. Wait a bit and try again."
        )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise UpdateError(f"GitHub returned an error checking for updates ({resp.status_code})") from exc
    data = resp.json()

    latest_sha = data["sha"]
    current = get_installed_version()
    return {
        "repo": config["repo"],
        "branch": config["branch"],
        "current_version": current,
        "latest_version": latest_sha,
        "update_available": latest_sha != current,
        "latest_message": data["commit"]["message"].splitlines()[0],
        "latest_date": data["commit"]["author"]["date"],
    }


# ---- applying --------------------------------------------------------------------

def apply_update(*, install_deps=None, build_frontend=None, on_restart=None,
                  backend_dir: Path = BACKEND_DIR, frontend_dir: Path = FRONTEND_DIR) -> dict:
    """The three callables are injectable so tests can swap in fakes for the
    slow/networked/subprocess-running parts while still exercising the real
    download, validation, and file-swap logic."""
    install_deps = install_deps or _install_backend_deps
    build_frontend = build_frontend or _build_frontend
    on_restart = on_restart or _schedule_process_restart

    check = check_for_update()
    target_sha = check["latest_version"]
    config = check

    with tempfile.TemporaryDirectory(prefix="agent-hub-update-") as tmp:
        tmp_path = Path(tmp)
        tarball_path = tmp_path / "source.tar.gz"
        _download_tarball(config["repo"], target_sha, tarball_path)

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        _extract_tarball(tarball_path, extract_dir)

        staged_root = _find_repo_root(extract_dir)
        staged_backend = staged_root / "backend"
        staged_frontend = staged_root / "frontend"
        _validate_staged_repo(staged_backend, staged_frontend)

        # everything above can fail without having touched the live install at all
        install_deps(staged_backend / "requirements.txt")
        build_frontend(staged_frontend)
        _swap_in_new_code(staged_backend, staged_frontend, backend_dir, frontend_dir)

    db.set_setting("installed_version", target_sha)
    restarting = on_restart()

    return {"updated_to": target_sha, "auto_restarting": bool(restarting)}


def _download_tarball(repo: str, ref: str, dest: Path) -> None:
    url = f"{GITHUB_API}/repos/{repo}/tarball/{ref}"
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=60) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)
    except httpx.HTTPError as exc:
        raise UpdateError(f"Couldn't download the update from GitHub: {exc}") from exc


def _extract_tarball(tarball_path: Path, dest_dir: Path) -> None:
    with tarfile.open(tarball_path) as tar:
        try:
            tar.extractall(dest_dir, filter="data")  # py3.12+: refuses path traversal etc.
        except TypeError:
            tar.extractall(dest_dir)  # older Python without the `filter` kwarg


def _find_repo_root(extract_dir: Path) -> Path:
    entries = [p for p in extract_dir.iterdir() if p.is_dir()]
    if len(entries) != 1:
        raise UpdateError("Unexpected archive layout from GitHub - expected one top-level folder")
    return entries[0]


def _validate_staged_repo(staged_backend: Path, staged_frontend: Path) -> None:
    required = [
        staged_backend / "app" / "main.py",
        staged_backend / "requirements.txt",
        staged_frontend / "package.json",
        staged_frontend / "src",
    ]
    missing = [str(p.relative_to(staged_backend.parent)) for p in required if not p.exists()]
    if missing:
        raise UpdateError(f"This doesn't look like an Agent Hub repository - missing: {', '.join(missing)}")


def _install_backend_deps(requirements_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        raise UpdateError(f"Installing updated dependencies failed:\n{result.stderr[-2000:]}")


def _build_frontend(staged_frontend_dir: Path) -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise UpdateError("npm isn't installed on this hub - can't build the updated frontend")
    for args in (["install"], ["run", "build"]):
        result = subprocess.run(
            [npm, *args], cwd=staged_frontend_dir, capture_output=True, text=True, timeout=900,
        )
        if result.returncode != 0:
            raise UpdateError(f"Building the frontend failed ({' '.join(args)}):\n{result.stderr[-2000:]}")


def _swap_in_new_code(staged_backend: Path, staged_frontend: Path,
                       backend_dir: Path, frontend_dir: Path) -> None:
    """The only step that touches the live installation - by design, just a
    handful of directory moves, so the window where things could go wrong is
    as small as possible. Keeps one backup of the previous app/ around
    (app.bak) as a manual rollback path if a new version turns out broken."""
    live_app = backend_dir / "app"
    backup_app = backend_dir / "app.bak"
    if backup_app.exists():
        shutil.rmtree(backup_app)
    if live_app.exists():
        shutil.move(str(live_app), str(backup_app))
    shutil.move(str(staged_backend / "app"), str(live_app))

    # the freshly built frontend belongs in app/static, whether or not the
    # repo itself tracks build output
    built_static = staged_frontend / "dist"
    if built_static.exists():
        dest_static = live_app / "static"
        if dest_static.exists():
            shutil.rmtree(dest_static)
        shutil.move(str(built_static), str(dest_static))

    shutil.copy2(staged_backend / "requirements.txt", backend_dir / "requirements.txt")

    live_frontend_src = frontend_dir / "src"
    if live_frontend_src.exists():
        shutil.rmtree(live_frontend_src)
    shutil.move(str(staged_frontend / "src"), str(live_frontend_src))
    shutil.copy2(staged_frontend / "package.json", frontend_dir / "package.json")


def _running_under_systemd() -> bool:
    # systemd sets this for every unit it manages - a reliable, zero-config
    # way to know whether exiting will actually bring us back up
    # (Restart=always) or just... exit.
    return "INVOCATION_ID" in os.environ


def _schedule_process_restart() -> bool:
    if not _running_under_systemd():
        return False

    def _delayed_exit():
        time.sleep(1.5)  # let the HTTP response confirming success reach the browser first
        os._exit(0)

    threading.Thread(target=_delayed_exit, daemon=True).start()
    return True
