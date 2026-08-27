"""
Per-user overrides of the hub-wide defaults from hub_settings.py: their
own OpenRouter API key (so usage bills to their own account, not a
shared one), and their own Tavily/YouTube keys (so a member without
admin rights can still use Web search/YouTube nodes in their own flows,
rather than being stuck if an admin hasn't set one hub-wide, or not
wanting to share their personal search quota with the whole team).

Google has no personal-override concept anymore - it authenticates
entirely through the one hub-wide service account (see
service_account_auth.py and hub_settings.py), which isn't the kind of
credential that makes sense to have a personal alternative to.

Personal settings win whenever they're fully set; otherwise everything
falls back to the hub-wide default exactly as before this existed - nobody
has to configure anything personal for the hub to keep working the way it
already did.
"""
from . import crypto_vault, db, hub_settings


def get_personal_settings(user_id: str) -> dict:
    return {
        "openrouter_model": db.get_user_setting(user_id, "openrouter_model") or "",
        "openrouter_key_configured": db.get_user_setting(user_id, "openrouter_api_key_encrypted") is not None,
        "web_search_key_configured": db.get_user_setting(user_id, "web_search_api_key_encrypted") is not None,
        "youtube_key_configured": db.get_user_setting(user_id, "youtube_api_key_encrypted") is not None,
    }


def update_personal_settings(user_id: str, *, openrouter_api_key: str | None = None,
                              openrouter_model: str | None = None,
                              web_search_api_key: str | None = None,
                              youtube_api_key: str | None = None) -> None:
    if openrouter_model is not None:
        db.set_user_setting(user_id, "openrouter_model", openrouter_model)
    if openrouter_api_key:  # only overwrite if a new one was actually provided
        db.set_user_setting(user_id, "openrouter_api_key_encrypted", crypto_vault.encrypt(openrouter_api_key).decode())
    if web_search_api_key:  # only overwrite if a new one was actually provided
        db.set_user_setting(user_id, "web_search_api_key_encrypted", crypto_vault.encrypt(web_search_api_key).decode())
    if youtube_api_key:  # only overwrite if a new one was actually provided
        db.set_user_setting(user_id, "youtube_api_key_encrypted", crypto_vault.encrypt(youtube_api_key).decode())


def clear_personal_openrouter_key(user_id: str) -> None:
    db.delete_user_setting(user_id, "openrouter_api_key_encrypted")


def clear_personal_web_search_key(user_id: str) -> None:
    db.delete_user_setting(user_id, "web_search_api_key_encrypted")


def clear_personal_youtube_key(user_id: str) -> None:
    db.delete_user_setting(user_id, "youtube_api_key_encrypted")


def resolve_openrouter_credentials(user_id: str | None) -> tuple[str | None, str]:
    """Returns (api_key, model). Personal key wins if set; otherwise hub-wide."""
    if user_id:
        personal_key_enc = db.get_user_setting(user_id, "openrouter_api_key_encrypted")
        if personal_key_enc:
            api_key = crypto_vault.decrypt(personal_key_enc.encode())
            model = db.get_user_setting(user_id, "openrouter_model") or hub_settings.get_settings()["openrouter_model"]
            return api_key, model
    return hub_settings.get_openrouter_api_key(), hub_settings.get_settings()["openrouter_model"]


def resolve_web_search_api_key(user_id: str | None) -> str | None:
    """Personal key wins if set; otherwise the hub-wide one."""
    if user_id:
        personal_key_enc = db.get_user_setting(user_id, "web_search_api_key_encrypted")
        if personal_key_enc:
            return crypto_vault.decrypt(personal_key_enc.encode())
    return hub_settings.get_web_search_api_key()


def resolve_youtube_api_key(user_id: str | None) -> str | None:
    """Personal key wins if set; otherwise the hub-wide one."""
    if user_id:
        personal_key_enc = db.get_user_setting(user_id, "youtube_api_key_encrypted")
        if personal_key_enc:
            return crypto_vault.decrypt(personal_key_enc.encode())
    return hub_settings.get_youtube_api_key()
