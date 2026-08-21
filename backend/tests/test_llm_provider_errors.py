"""
Regression test for a bug found via a live screenshot: an LLM provider HTTP
error (bad API key, unknown model, provider down) used to leak straight
through as a raw httpx exception string ("Client error '403 Forbidden' for
url 'https://openrouter.ai/...'") instead of a clean, actionable message.
Run with: python3 tests/test_llm_provider_errors.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-llmerr-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import db, hub_settings, llm_provider  # noqa: E402
from app.main import app  # noqa: E402

db.init_db()


class FakeErrorResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def raise_for_status(self):
        raise httpx.HTTPStatusError(
            f"Client error '{self.status_code} ...' for url 'https://openrouter.ai/api/v1/chat/completions'",
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
            response=httpx.Response(self.status_code, request=httpx.Request("POST", "https://x")),
        )


def fake_post_factory(status_code):
    def fake_post(url, **kwargs):
        return FakeErrorResponse(status_code)
    return fake_post


def main():
    hub_settings.update_settings(llm_provider="openrouter", openrouter_api_key="bad-key", openrouter_model="test/model")

    # --- a 403 (or 401) gives a clean, specific message - not raw httpx text ---
    with patch("httpx.post", side_effect=fake_post_factory(403)):
        try:
            llm_provider.chat_completion([{"role": "user", "content": "hi"}])
            raised = None
        except llm_provider.LlmNotConfigured as exc:
            raised = str(exc)
    assert raised is not None
    assert "Client error" not in raised, f"raw httpx text leaked through: {raised}"
    assert "https://openrouter.ai" not in raised, f"raw URL leaked through: {raised}"
    assert "403" in raised and "openrouter" in raised.lower() and "Settings" in raised
    print(f"[ok] a 403 gives a clean message: \"{raised}\"")

    # --- a 404 (bad model name) gets its own specific message ---
    with patch("httpx.post", side_effect=fake_post_factory(404)):
        try:
            llm_provider.chat_completion([{"role": "user", "content": "hi"}], model="not/a-real-model")
            raised2 = None
        except llm_provider.LlmNotConfigured as exc:
            raised2 = str(exc)
    assert raised2 is not None and "model" in raised2.lower() and "not/a-real-model" in raised2
    print(f"[ok] a 404 gives a model-specific message: \"{raised2}\"")

    # --- a network-level failure (unreachable host) is also cleaned up ---
    def fake_connect_error(url, **kwargs):
        raise httpx.ConnectError("Connection refused", request=httpx.Request("POST", url))
    with patch("httpx.post", side_effect=fake_connect_error):
        try:
            llm_provider.chat_completion([{"role": "user", "content": "hi"}])
            raised3 = None
        except llm_provider.LlmNotConfigured as exc:
            raised3 = str(exc)
    assert raised3 is not None and "Couldn't reach" in raised3
    print(f"[ok] a connection failure gives a clean message: \"{raised3}\"")

    print("\nAll LLM-provider error-handling smoke tests passed.")


if __name__ == "__main__":
    main()
