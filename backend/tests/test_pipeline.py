"""
End-to-end smoke test for the ingestion + query pipeline, using a deterministic
fake embedder so it runs offline (no downloading the real ONNX model). Run with:

    AGENT_HUB_DATA_DIR=/tmp/agent-hub-test python3 tests/test_pipeline.py
"""
import hashlib
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, embeddings  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


class FakeEmbeddingProvider:
    """Deterministic, offline embedding: hash each text into a small fixed vector.
    Good enough to prove ingestion/retrieval wiring works without a network call."""

    DIM = 32

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vec = [digest[i % len(digest)] / 255.0 for i in range(self.DIM)]
            out.append(vec)
        return out


def main():
    embeddings.set_embedding_provider(FakeEmbeddingProvider())
    client = TestClient(app)
    headers = auth_headers(client, "Alex")

    me = client.get("/api/me", headers=headers).json()
    assert me["name"] == "Alex", me
    print(f"[ok] identified as user: {me}")

    kb = client.post(
        "/api/knowledge-bases",
        json={"name": "Team handbook", "description": "Onboarding docs", "visibility": "shared"},
        headers=headers,
    ).json()
    assert kb["name"] == "Team handbook", kb
    print(f"[ok] created knowledge base: {kb['id']}")

    sample_text = (
        "The vacation policy allows 20 days of paid time off per year.\n\n"
        "Employees must submit requests at least two weeks in advance.\n\n"
        "The office WiFi password is rotated every quarter and posted on the intranet.\n\n"
        "Reimbursements for travel are processed within 10 business days."
    )
    files = {"file": ("handbook.txt", sample_text, "text/plain")}
    doc = client.post(f"/api/knowledge-bases/{kb['id']}/documents", files=files, headers=headers).json()
    print(f"[ok] uploaded document: {doc['id']} (status={doc['status']})")

    # background task runs inline under TestClient, but poll briefly just in case
    for _ in range(20):
        doc = client.get(f"/api/knowledge-bases/{kb['id']}/documents", headers=headers).json()[0]
        if doc["status"] in ("ready", "failed"):
            break
        time.sleep(0.2)
    assert doc["status"] == "ready", doc
    assert doc["chunk_count"] > 0, doc
    print(f"[ok] ingestion finished: {doc['chunk_count']} chunks")

    result = client.post(
        f"/api/knowledge-bases/{kb['id']}/query",
        json={"query": "how many vacation days do I get", "top_k": 2},
        headers=headers,
    ).json()
    assert len(result["results"]) > 0, result
    print(f"[ok] query returned {len(result['results'])} chunks, top hit:")
    print(f"     -> {result['results'][0]['text'][:80]}...")

    # a second, unauthenticated-looking user should still see the shared KB
    other_headers = auth_headers(client, "Sam")
    kbs_for_sam = client.get("/api/knowledge-bases", headers=other_headers).json()
    assert any(k["id"] == kb["id"] for k in kbs_for_sam), kbs_for_sam
    print("[ok] shared knowledge base is visible to a second team member")

    # a private KB should NOT be visible to Sam
    private_kb = client.post(
        "/api/knowledge-bases",
        json={"name": "Alex's scratchpad", "visibility": "private"},
        headers=headers,
    ).json()
    kbs_for_sam = client.get("/api/knowledge-bases", headers=other_headers).json()
    assert not any(k["id"] == private_kb["id"] for k in kbs_for_sam)
    denied = client.get(f"/api/knowledge-bases/{private_kb['id']}/documents", headers=other_headers)
    assert denied.status_code == 403, denied.text
    print("[ok] private knowledge base is hidden and access-denied for another team member")

    # Alex was the first user ever created -> should have been auto-promoted to admin
    alex_profile = client.get("/api/me", headers=headers).json()
    assert alex_profile["role"] == "admin", alex_profile
    print("[ok] first user on the hub was auto-promoted to admin")

    # admin (Alex) can see and reach Sam's future private KB too, for support
    sam_private_kb = client.post(
        "/api/knowledge-bases",
        json={"name": "Sam's scratchpad", "visibility": "private"},
        headers=other_headers,
    ).json()
    kbs_for_alex = client.get("/api/knowledge-bases", headers=headers).json()
    assert any(k["id"] == sam_private_kb["id"] for k in kbs_for_alex)
    allowed = client.get(f"/api/knowledge-bases/{sam_private_kb['id']}/documents", headers=headers)
    assert allowed.status_code == 200, allowed.text
    print("[ok] hub admin can see and access another member's private knowledge base")

    # a non-admin can't promote anyone
    forbidden = client.patch("/api/users/sam/role?role=admin", headers=other_headers)
    assert forbidden.status_code == 403, forbidden.text
    promoted = client.patch("/api/users/sam/role?role=admin", headers=headers)
    assert promoted.status_code == 200, promoted.text
    print("[ok] role promotion is admin-only and works for an admin")

    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    main()
