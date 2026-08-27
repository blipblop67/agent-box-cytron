"""
Central configuration, all overridable via environment variables so the same
code runs unchanged on a dev laptop or on the Pi.

Loads backend/.env automatically (if present) before reading anything, so
editing that file and restarting is enough on Windows or Linux alike -
without this, only systemd's EnvironmentFile (Pi-only) would ever actually
pick it up. Real environment variables still win if both are set.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR = Path(os.getenv("AGENT_HUB_DATA_DIR", str(Path.home() / ".agent-hub")))
UPLOAD_DIR = BASE_DIR / "uploads"
CHROMA_DIR = BASE_DIR / "chroma"
SQLITE_PATH = BASE_DIR / "agent_hub.db"

# "local"  -> runs a small ONNX embedding model on-device via fastembed (no GPU/torch needed,
#             fine on a Pi 5 CPU). Good default for a self-contained hub.
# "ollama" -> calls an Ollama server's /api/embeddings endpoint, useful if the user already
#             points their hub at a beefier machine for chat and wants embeddings there too.
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")
LOCAL_EMBEDDING_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "120"))
DEFAULT_TOP_K = int(os.getenv("RAG_DEFAULT_TOP_K", "5"))

MAX_UPLOAD_MB = int(os.getenv("RAG_MAX_UPLOAD_MB", "50"))
ALLOWED_EXTENSIONS = {".pdf", ".csv", ".docx", ".txt", ".md"}

for _d in (UPLOAD_DIR, CHROMA_DIR):
    _d.mkdir(parents=True, exist_ok=True)
