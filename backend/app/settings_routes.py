from fastapi import APIRouter, Depends, HTTPException, Request

from . import gmail_routes, drive_routes, google_oauth, hub_settings
from .auth import get_current_user
from .models import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


def _settings_out(request: Request) -> dict:
    settings = hub_settings.get_settings()
    settings["google_email_redirect_uri"] = google_oauth.redirect_uri_for(request, gmail_routes.CALLBACK_PATH)
    settings["google_drive_redirect_uri"] = google_oauth.redirect_uri_for(request, drive_routes.CALLBACK_PATH)
    return settings


@router.get("", response_model=SettingsOut)
def get_settings(request: Request, user: dict = Depends(get_current_user)):
    return _settings_out(request)


@router.put("", response_model=SettingsOut)
def update_settings(request: Request, body: SettingsUpdate, user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(403, "Only a hub admin can change hub settings")
    hub_settings.update_settings(**body.model_dump())
    return _settings_out(request)
