"""
Basic defense-in-depth for anyone who's given the hub a real DNS name
(DuckDNS, Tailscale, etc.) - proves robots.txt disallows everything and
every response carries a noindex header, so a search engine that
somehow does reach the hub is told not to index anything.
Run with: python3 tests/test_robots_hardening.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-robots-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

db.init_db()


def main():
    client = TestClient(app)

    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert "Disallow: /" in robots.text
    print(f"[ok] /robots.txt disallows everything: {robots.text!r}")

    healthz = client.get("/healthz")
    assert healthz.headers.get("x-robots-tag") == "noindex, nofollow"
    print("[ok] the noindex header is present even on an unauthenticated endpoint")

    api_response = client.get("/api/settings")  # 401, unauthenticated - header should still be there
    assert api_response.headers.get("x-robots-tag") == "noindex, nofollow"
    print("[ok] the noindex header is present on API responses too, regardless of status code")

    print("\nAll robots/noindex hardening smoke tests passed.")


if __name__ == "__main__":
    main()
