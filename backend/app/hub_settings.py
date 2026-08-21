"""
Hub-wide settings an admin sets once from the Settings page, instead of
editing config files: the LLM provider, and Google OAuth app credentials for
Gmail/Drive. Secrets (OpenRouter key, Google client secret) are encrypted at
rest with the same vault used for OAuth tokens.

Google's redirect URIs are deliberately *not* a setting here - they're
derived from the request that hits /auth/start (see gmail_routes.py /
drive_routes.py), so there's nothing to keep in sync with however someone
happens to be reached (hostname, IP, port). The Settings page shows the
computed values so there's something exact to paste into Google Cloud
Console.
"""
from . import config, crypto_vault, db

DEFAULTS = {
    "llm_provider": "openrouter",         # "openrouter" | "ollama"
    "openrouter_model": "",               # e.g. "anthropic/claude-3.5-haiku" - admin picks
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "",                   # e.g. "llama3.1" - admin picks whatever they've pulled
    "google_client_id": "",
}


def get_settings() -> dict:
    settings = dict(DEFAULTS)
    for key in DEFAULTS:
        value = db.get_setting(key)
        if value is not None:
            settings[key] = value
    # env vars are a fallback for people who'd rather configure via .env /
    # systemd than the UI - the UI always takes priority once someone uses it
    if not settings["google_client_id"]:
        settings["google_client_id"] = config.GOOGLE_CLIENT_ID
    settings["openrouter_key_configured"] = db.get_setting("openrouter_api_key_encrypted") is not None
    settings["google_client_secret_configured"] = (
        db.get_setting("google_client_secret_encrypted") is not None or bool(config.GOOGLE_CLIENT_SECRET)
    )
    return settings


def update_settings(*, llm_provider: str | None = None, openrouter_api_key: str | None = None,
                     openrouter_model: str | None = None, ollama_base_url: str | None = None,
                     ollama_model: str | None = None, google_client_id: str | None = None,
                     google_client_secret: str | None = None) -> None:
    if llm_provider is not None:
        db.set_setting("llm_provider", llm_provider)
    if openrouter_model is not None:
        db.set_setting("openrouter_model", openrouter_model)
    if ollama_base_url is not None:
        db.set_setting("ollama_base_url", ollama_base_url)
    if ollama_model is not None:
        db.set_setting("ollama_model", ollama_model)
    if openrouter_api_key:  # only overwrite if a new one was actually provided
        db.set_setting("openrouter_api_key_encrypted", crypto_vault.encrypt(openrouter_api_key).decode())
    if google_client_id is not None:
        db.set_setting("google_client_id", google_client_id)
    if google_client_secret:  # only overwrite if a new one was actually provided
        db.set_setting("google_client_secret_encrypted", crypto_vault.encrypt(google_client_secret).decode())


def get_openrouter_api_key() -> str | None:
    stored = db.get_setting("openrouter_api_key_encrypted")
    if stored is None:
        return None
    return crypto_vault.decrypt(stored.encode())


def get_google_client_id() -> str:
    return db.get_setting("google_client_id") or config.GOOGLE_CLIENT_ID or ""


def get_google_client_secret() -> str:
    stored = db.get_setting("google_client_secret_encrypted")
    if stored:
        return crypto_vault.decrypt(stored.encode())
    return config.GOOGLE_CLIENT_SECRET or ""
