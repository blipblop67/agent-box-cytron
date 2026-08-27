"""
"My account": the personal overrides from user_settings.py, exposed to
whoever's logged in for their own account only - nobody can see or set
these for anyone else, including admins (unlike hub_settings.py, which is
admin-only precisely because it's shared).

Google has no personal setting anymore - it's a single hub-wide service
account (see hub_settings.py / service_account_auth.py), not something
that makes sense to override per person.
"""
from fastapi import APIRouter, Depends

from . import user_settings
from .auth import get_current_user
from .models import PersonalSettingsOut, PersonalSettingsUpdate

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/settings", response_model=PersonalSettingsOut)
def get_my_settings(user: dict = Depends(get_current_user)):
    return user_settings.get_personal_settings(user["id"])


@router.put("/settings", response_model=PersonalSettingsOut)
def update_my_settings(body: PersonalSettingsUpdate, user: dict = Depends(get_current_user)):
    user_settings.update_personal_settings(user["id"], **body.model_dump())
    return user_settings.get_personal_settings(user["id"])
