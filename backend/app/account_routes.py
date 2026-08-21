"""
"My account": the personal overrides from user_settings.py, exposed to
whoever's logged in for their own account only - nobody can see or set
these for anyone else, including admins (unlike hub_settings.py, which is
admin-only precisely because it's shared).
"""
from fastapi import APIRouter, Depends, Request

from . import gmail_routes, drive_routes, calendar_routes, google_oauth, user_settings
from .auth import get_current_user
from .models import PersonalSettingsOut, PersonalSettingsUpdate

router = APIRouter(prefix="/account", tags=["account"])


def _personal_settings_out(user_id: str, request: Request) -> dict:
    settings = user_settings.get_personal_settings(user_id)
    settings["google_email_redirect_uri"] = google_oauth.redirect_uri_for(request, gmail_routes.CALLBACK_PATH)
    settings["google_drive_redirect_uri"] = google_oauth.redirect_uri_for(request, drive_routes.CALLBACK_PATH)
    settings["google_calendar_redirect_uri"] = google_oauth.redirect_uri_for(request, calendar_routes.CALLBACK_PATH)
    return settings


@router.get("/settings", response_model=PersonalSettingsOut)
def get_my_settings(request: Request, user: dict = Depends(get_current_user)):
    return _personal_settings_out(user["id"], request)


@router.put("/settings", response_model=PersonalSettingsOut)
def update_my_settings(request: Request, body: PersonalSettingsUpdate, user: dict = Depends(get_current_user)):
    user_settings.update_personal_settings(user["id"], **body.model_dump())
    return _personal_settings_out(user["id"], request)
