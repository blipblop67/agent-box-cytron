"""
One interface, two backends. OpenRouter doesn't expose an embeddings endpoint,
so RAG needs its own model - either small and local (fine on a Pi 5 CPU, no GPU
or torch required) or delegated to whatever machine is already running Ollama
for chat.
"""
from abc import ABC, abstractmethod

import httpx

from . import config


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class LocalEmbeddingProvider(EmbeddingProvider):
    """fastembed runs a small ONNX model directly on-device - no PyTorch, no GPU,
    and the model (~130MB for bge-small) is cached after the first download."""

    def __init__(self, model_name: str = config.LOCAL_EMBEDDING_MODEL):
        from fastembed import TextEmbedding
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._model.embed(texts)]


class OllamaEmbeddingProvider(EmbeddingProvider):
    def __init__(self, base_url: str = config.OLLAMA_BASE_URL, model: str = config.OLLAMA_EMBEDDING_MODEL):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.Client(timeout=60)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            resp = self._client.post(
                f"{self._base_url}/api/embeddings",
                json={"model": self._model, "prompt": text},
            )
            resp.raise_for_status()
            out.append(resp.json()["embedding"])
        return out


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """Lazily created and cached - the local model is slow to load, we only want
    to pay that cost once per process, not once per request."""
    global _provider
    if _provider is None:
        if config.EMBEDDING_PROVIDER == "ollama":
            _provider = OllamaEmbeddingProvider()
        else:
            _provider = LocalEmbeddingProvider()
    return _provider


def set_embedding_provider(provider: EmbeddingProvider) -> None:
    """Test/override hook - lets tests (or an admin settings screen) swap the
    provider without touching env vars."""
    global _provider
    _provider = provider
