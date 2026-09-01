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

    try:
        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json={"model": model, "messages": messages, "temperature": temperature},
            timeout=120,  # local/small models can be slow, especially on a first cold load
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            where = "Settings" if provider == "openrouter" and not user_id else "Settings or your Account page"
            raise LlmNotConfigured(f"{provider} rejected the request ({status}) - double-check the API key on {where}") from exc
        if status == 404:
            raise LlmNotConfigured(f"{provider} doesn't recognize the model '{model}' - check it's spelled right and available") from exc
        if status == 429:
            hint = " - a free/no-cost model shares a strict limit across everyone using it; adding credits or switching model usually fixes this" if provider == "openrouter" else ""
            raise LlmNotConfigured(f"{provider} is rate-limiting these requests (429){hint}. Wait a bit and try again") from exc
        raise LlmNotConfigured(f"{provider} request failed ({status})") from exc
    except httpx.HTTPError as exc:
        raise LlmNotConfigured(f"Couldn't reach {provider}: {exc}") from exc

    data = resp.json()
    return data["choices"][0]["message"]["content"]
