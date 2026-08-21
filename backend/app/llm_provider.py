"""
One client for both providers. Ollama exposes an OpenAI-compatible
/v1/chat/completions endpoint, and OpenRouter is fully OpenAI-compatible too -
so the only thing that changes between them is base_url, an API key, and the
model name. No SDK needed, just httpx.
"""
import httpx

from . import hub_settings, user_settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class LlmNotConfigured(Exception):
    pass


def chat_completion(messages: list[dict], *, model: str | None = None, provider: str | None = None,
                     user_id: str | None = None, temperature: float = 0.7) -> str:
    """messages: [{"role": "system"|"user"|"assistant", "content": "..."}]. `model`
    and `provider` override the hub-wide default for this one call (a flow's LLM
    node can pin its own model without touching hub settings). `user_id`, when
    given, lets a personal OpenRouter key (Account page) take priority over the
    hub-wide one - Ollama has no per-user equivalent, since it's shared
    infrastructure rather than a billed-per-account API."""
    settings = hub_settings.get_settings()
    provider = provider or settings["llm_provider"]

    if provider == "ollama":
        base_url = settings["ollama_base_url"].rstrip("/")
        model = model or settings["ollama_model"]
        if not model:
            raise LlmNotConfigured("No Ollama model configured - set one in Settings or on the LLM node")
        headers = {}
    elif provider == "openrouter":
        api_key, default_model = user_settings.resolve_openrouter_credentials(user_id)
        if not api_key:
            raise LlmNotConfigured("No OpenRouter API key configured - add one in Settings or your Account page")
        base_url = OPENROUTER_BASE_URL
        model = model or default_model
        if not model:
            raise LlmNotConfigured("No OpenRouter model configured - set one in Settings, Account, or on the LLM node")
        headers = {"Authorization": f"Bearer {api_key}"}
    else:
        raise LlmNotConfigured(f"Unknown provider '{provider}'")

    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json={"model": model, "messages": messages, "temperature": temperature},
        timeout=120,  # local/small models can be slow, especially on a first cold load
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]
