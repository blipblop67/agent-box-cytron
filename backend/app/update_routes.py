from fastapi import APIRouter, Depends, HTTPException

from . import updater
from .auth import get_current_user
from .models import UpdateApplyResult, UpdateConfigRequest, UpdateStatus

router = APIRouter(prefix="/updates", tags=["updates"])


def _require_admin(user: dict):
    if user["role"] != "admin":
        raise HTTPException(403, "Only a hub admin can manage software updates")


@router.get("/status", response_model=UpdateStatus)
def status(user: dict = Depends(get_current_user)):
    config = updater.get_update_config()
    try:
        return UpdateStatus(**updater.check_for_update(), configured=True)
    except updater.UpdateError as exc:
        # a failed check (repo not public yet, network hiccup, rate limit) is
        # something to show on the page, not a reason to break it entirely -
        # this fires on every page load now that there's always a default repo
        return UpdateStatus(
            repo=config["repo"], branch=config["branch"], current_version=updater.get_installed_version(),
            configured=True, error=str(exc),
        )


@router.put("/config", response_model=UpdateStatus)
def configure(body: UpdateConfigRequest, user: dict = Depends(get_current_user)):
    _require_admin(user)
    updater.set_update_config(body.repo, body.branch)
    try:
        return UpdateStatus(**updater.check_for_update(), configured=True)
    except updater.UpdateError as exc:
        raise HTTPException(400, str(exc))


@router.post("/check", response_model=UpdateStatus)
def check(user: dict = Depends(get_current_user)):
    _require_admin(user)
    try:
        return UpdateStatus(**updater.check_for_update(), configured=True)
    except updater.UpdateError as exc:
        raise HTTPException(400, str(exc))


@router.post("/apply", response_model=UpdateApplyResult)
def apply(user: dict = Depends(get_current_user)):
    _require_admin(user)
    try:
        return updater.apply_update()
    except updater.UpdateError as exc:
        raise HTTPException(400, str(exc))
