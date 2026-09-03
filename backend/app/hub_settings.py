"""
Hub-wide settings an admin sets once from the Settings page, instead of
editing config files: the LLM provider, a Google service account key
(the only way this hub talks to Google - see service_account_auth.py), a
web search API key, a YouTube API key, and outgoing SMTP settings (for
password-reset emails). Secrets (OpenRouter key, the service account
key, Tavily key, YouTube key, SMTP password) are encrypted at rest with
the same vault used elsewhere in this hub.
"""
from . import crypto_vault, db, service_account_auth

DEFAULTS = {
    "hub_name": "",                       # shown in the sidebar/tab title - how someone tells this hub apart from another one
    "llm_provider": "openrouter",         # "openrouter" | "ollama"
    "openrouter_model": "",               # e.g. "anthropic/claude-3.5-haiku" - admin picks
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "",                   # e.g. "llama3.1" - admin picks whatever they've pulled
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_username": "",
    "smtp_from_address": "",
    "smtp_use_tls": "true",               # "true" -> STARTTLS on smtp_port (587 typical); "false" -> implicit TLS (465 typical)
    "duckdns_subdomain": "",
    "google_oauth_client_id": "",
}


def get_settings() -> dict:
    settings = dict(DEFAULTS)
    for key in DEFAULTS:
        value = db.get_setting(key)
        if value is not None:
            settings[key] = value
    settings["openrouter_key_configured"] = db.get_setting("openrouter_api_key_encrypted") is not None
    settings["web_search_key_configured"] = db.get_setting("web_search_api_key_encrypted") is not None
    settings["youtube_key_configured"] = db.get_setting("youtube_api_key_encrypted") is not None
    settings["smtp_use_tls"] = settings["smtp_use_tls"] == "true"
    settings["smtp_password_configured"] = db.get_setting("smtp_password_encrypted") is not None
    settings["smtp_configured"] = bool(settings["smtp_host"] and settings["smtp_from_address"])
    stored_key = db.get_setting("google_service_account_key_encrypted")
    settings["google_service_account_configured"] = stored_key is not None
    settings["google_service_account_email"] = ""
    if stored_key:
        try:
            settings["google_service_account_email"] = service_account_auth.parse_key(
                crypto_vault.decrypt(stored_key.encode())
            )["client_email"]
        except service_account_auth.ServiceAccountError:
            pass  # a corrupted stored key shouldn't crash the settings page - just shows blank
    settings["duckdns_token_configured"] = db.get_setting("duckdns_token_encrypted") is not None
    settings["duckdns_configured"] = bool(settings["duckdns_subdomain"]) and settings["duckdns_token_configured"]
    settings["duckdns_last_updated_ip"] = db.get_setting("duckdns_last_updated_ip") or ""
    last_updated_at = db.get_setting("duckdns_last_updated_at")
    settings["duckdns_last_updated_at"] = float(last_updated_at) if last_updated_at else None
    settings["duckdns_last_error"] = db.get_setting("duckdns_last_error") or ""
    settings["google_oauth_client_secret_configured"] = db.get_setting("google_oauth_client_secret_encrypted") is not None
    return settings


def update_settings(*, hub_name: str | None = None, llm_provider: str | None = None, openrouter_api_key: str | None = None,
                     openrouter_model: str | None = None, ollama_base_url: str | None = None,
                     ollama_model: str | None = None, web_search_api_key: str | None = None,
                     youtube_api_key: str | None = None, smtp_host: str | None = None,
                     smtp_port: str | None = None, smtp_username: str | None = None,
                     smtp_password: str | None = None, smtp_from_address: str | None = None,
                     smtp_use_tls: bool | None = None, google_service_account_key: str | None = None,
                     duckdns_subdomain: str | None = None, duckdns_token: str | None = None,
                     google_oauth_client_id: str | None = None, google_oauth_client_secret: str | None = None) -> None:
    if hub_name is not None:
        db.set_setting("hub_name", hub_name.strip()[:60])  # a short label, not a paragraph
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
    if web_search_api_key:  # only overwrite if a new one was actually provided
        db.set_setting("web_search_api_key_encrypted", crypto_vault.encrypt(web_search_api_key).decode())
    if youtube_api_key:  # only overwrite if a new one was actually provided
        db.set_setting("youtube_api_key_encrypted", crypto_vault.encrypt(youtube_api_key).decode())
    if smtp_host is not None:
        db.set_setting("smtp_host", smtp_host)
    if smtp_port is not None:
        db.set_setting("smtp_port", smtp_port)
    if smtp_username is not None:
        db.set_setting("smtp_username", smtp_username)
    if smtp_from_address is not None:
        db.set_setting("smtp_from_address", smtp_from_address)
    if smtp_use_tls is not None:
        db.set_setting("smtp_use_tls", "true" if smtp_use_tls else "false")
    if smtp_password:  # only overwrite if a new one was actually provided
        db.set_setting("smtp_password_encrypted", crypto_vault.encrypt(smtp_password).decode())
    if google_service_account_key:  # only overwrite if a new one was actually provided
        service_account_auth.parse_key(google_service_account_key)  # raises a clear error before storing garbage
        db.set_setting("google_service_account_key_encrypted", crypto_vault.encrypt(google_service_account_key).decode())
    if duckdns_subdomain is not None:
        db.set_setting("duckdns_subdomain", duckdns_subdomain)
    if duckdns_token:  # only overwrite if a new one was actually provided
        db.set_setting("duckdns_token_encrypted", crypto_vault.encrypt(duckdns_token).decode())
    if google_oauth_client_id is not None:
        db.set_setting("google_oauth_client_id", google_oauth_client_id)
    if google_oauth_client_secret:  # only overwrite if a new one was actually provided
        db.set_setting("google_oauth_client_secret_encrypted", crypto_vault.encrypt(google_oauth_client_secret).decode())


def get_openrouter_api_key() -> str | None:
    stored = db.get_setting("openrouter_api_key_encrypted")
    if stored is None:
        return None
    return crypto_vault.decrypt(stored.encode())


def get_web_search_api_key() -> str | None:
    stored = db.get_setting("web_search_api_key_encrypted")
    if stored is None:
        return None
    return crypto_vault.decrypt(stored.encode())


def get_youtube_api_key() -> str | None:
    stored = db.get_setting("youtube_api_key_encrypted")
    if stored is None:
        return None
    return crypto_vault.decrypt(stored.encode())


def get_smtp_settings() -> dict:
    """Shaped for email_sender.py to consume directly."""
    settings = get_settings()
    stored_password = db.get_setting("smtp_password_encrypted")
    return {
        "host": settings["smtp_host"],
        "port": int(settings["smtp_port"] or 587),
        "username": settings["smtp_username"],
        "password": crypto_vault.decrypt(stored_password.encode()) if stored_password else "",
        "from_address": settings["smtp_from_address"],
        "use_tls": settings["smtp_use_tls"],
        "configured": settings["smtp_configured"],
    }


def get_service_account_key() -> dict | None:
    """The parsed key dict service_account_auth.py needs, or None if
    nothing's configured yet. Callers should catch ServiceAccountError
    separately for a corrupted key - this only handles "not set up"."""
    stored = db.get_setting("google_service_account_key_encrypted")
    if stored is None:
        return None
    return service_account_auth.parse_key(crypto_vault.decrypt(stored.encode()))


def get_duckdns_credentials() -> tuple[str, str] | None:
    """(subdomain, token), or None if DuckDNS hasn't been set up - the one
    thing scheduler.py's periodic refresh job and the manual "update now"
    endpoint both need before calling dynamic_dns.update()."""
    subdomain = db.get_setting("duckdns_subdomain")
    token_enc = db.get_setting("duckdns_token_encrypted")
    if not subdomain or not token_enc:
        return None
    return subdomain, crypto_vault.decrypt(token_enc.encode())


def get_google_oauth_client() -> tuple[str | None, str | None]:
    """(client_id, client_secret) for this hub's own Google Cloud project -
    one per customer, same as the service account key is one per hub.
    Either half may be None if OAuth hasn't been set up; callers check for
    that themselves rather than this raising, since "not configured yet"
    is the default, expected state for most hubs."""
    client_id = db.get_setting("google_oauth_client_id")
    secret_enc = db.get_setting("google_oauth_client_secret_encrypted")
    secret = crypto_vault.decrypt(secret_enc.encode()) if secret_enc else None
    return client_id, secret

