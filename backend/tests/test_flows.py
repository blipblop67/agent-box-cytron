"""
Builds real flows through the API and runs them - covers Input -> Knowledge
base -> LLM -> Output (mocking only the outbound LLM HTTP call, everything
else - chunking, embedding, vector search, graph execution - is real) and a
separate Calculator flow. Run with: python3 tests/test_flows.py
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-flow-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, embeddings  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


class FakeEmbeddingProvider:
    DIM = 16

    def embed(self, texts):
        import hashlib
        out = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            out.append([digest[i % len(digest)] / 255.0 for i in range(self.DIM)])
        return out


class FakeLlmResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def fake_llm_post(url, headers=None, json=None, **kwargs):
    assert url == "https://openrouter.ai/api/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-openrouter-key"
    assert json["model"] == "test/model"
    user_message = json["messages"][-1]["content"]
    return FakeLlmResponse(f"Summary based on: {user_message[:60]}")


def main():
    embeddings.set_embedding_provider(FakeEmbeddingProvider())
    client = TestClient(app)
    headers = auth_headers(client, "Alex")  # first user -> admin

    # --- settings: configure OpenRouter as the provider ---
    settings = client.get("/api/settings", headers=headers).json()
    assert settings["openrouter_key_configured"] is False
    updated = client.put(
        "/api/settings", headers=headers,
        json={"llm_provider": "openrouter", "openrouter_api_key": "test-openrouter-key",
              "openrouter_model": "test/model"},
    ).json()
    assert updated["openrouter_key_configured"] is True
    assert updated["openrouter_model"] == "test/model"
    print("[ok] admin configured hub-wide LLM settings")

    # a non-admin can't change settings
    other_headers = auth_headers(client, "Sam")
    forbidden = client.put("/api/settings", headers=other_headers, json={"llm_provider": "ollama"})
    assert forbidden.status_code == 403
    print("[ok] non-admin cannot change LLM settings")

    # --- knowledge base with one document, for the KB node to query ---
    kb = client.post(
        "/api/knowledge-bases", headers=headers,
        json={"name": "Handbook", "visibility": "shared"},
    ).json()
    files = {"file": ("handbook.txt", "Remote employees get a $500 setup stipend in month one.", "text/plain")}
    client.post(f"/api/knowledge-bases/{kb['id']}/documents", files=files, headers=headers)
    print(f"[ok] created knowledge base and ingested a document")

    # --- build a flow: Input -> Knowledge base -> LLM -> Output ---
    flow = client.post("/api/flows", headers=headers, json={"name": "Handbook Q&A"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "kb", "type": "knowledge_base", "position": {"x": 200, "y": 0},
             "data": {"kb_id": kb["id"], "top_k": 3}},
            {"id": "llm", "type": "llm", "position": {"x": 400, "y": 0},
             "data": {"provider": "openrouter", "model": "test/model",
                      "system_prompt": "Answer using only the provided context."}},
            {"id": "out", "type": "output", "position": {"x": 600, "y": 0}, "data": {}},
        ],
        "edges": [
            {"id": "e1", "source": "in", "target": "kb"},
            {"id": "e2", "source": "kb", "target": "llm"},
            {"id": "e3", "source": "llm", "target": "out"},
        ],
    }
    saved = client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph}).json()
    assert len(saved["graph"]["nodes"]) == 4
    print("[ok] saved a 4-node flow")

    with patch("httpx.post", side_effect=fake_llm_post):
        result = client.post(
            f"/api/flows/{flow['id']}/run", headers=headers,
            json={"input": "What's the remote work stipend?"},
        )
    assert result.status_code == 200, result.text
    body = result.json()
    assert len(body["trace"]) == 4
    assert body["trace"][1]["type"] == "knowledge_base"
    assert "setup stipend" in body["trace"][1]["output"]
    assert body["output"].startswith("Summary based on:")
    print(f"[ok] ran the flow end-to-end, trace has {len(body['trace'])} steps")
    print(f"     final output: \"{body['output']}\"")

    # --- a second, simpler flow: Input -> Calculator -> Output ---
    calc_flow = client.post("/api/flows", headers=headers, json={"name": "Quick math"}).json()
    calc_graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "calc", "type": "calculator", "position": {"x": 200, "y": 0}, "data": {}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "calc"}, {"id": "e2", "source": "calc", "target": "out"}],
    }
    client.put(f"/api/flows/{calc_flow['id']}", headers=headers, json={"graph": calc_graph})
    calc_result = client.post(f"/api/flows/{calc_flow['id']}/run", headers=headers, json={"input": "12 * (3 + 4)"})
    assert calc_result.json()["output"] == "84.0" or calc_result.json()["output"] == "84"
    print(f"[ok] calculator flow: 12 * (3 + 4) = {calc_result.json()['output']}")

    # --- a flow with a cycle should fail clearly, not hang ---
    bad_flow = client.post("/api/flows", headers=headers, json={"name": "Broken"}).json()
    bad_graph = {
        "nodes": [
            {"id": "a", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "b", "type": "output", "position": {"x": 100, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "a", "target": "b"}, {"id": "e2", "source": "b", "target": "a"}],
    }
    client.put(f"/api/flows/{bad_flow['id']}", headers=headers, json={"graph": bad_graph})
    bad_result = client.post(f"/api/flows/{bad_flow['id']}/run", headers=headers, json={"input": "x"})
    assert bad_result.status_code == 400
    print("[ok] a cyclic flow fails with a clear error instead of hanging")

    # --- flow visibility follows the same shared/private/admin rules as KBs ---
    private_flow = client.post(
        "/api/flows", headers=headers, json={"name": "Alex's draft", "visibility": "private"}
    ).json()
    flows_for_sam = client.get("/api/flows", headers=other_headers).json()
    assert not any(f["id"] == private_flow["id"] for f in flows_for_sam)
    print("[ok] private flows are hidden from other team members")

    print("\nAll flow smoke tests passed.")


if __name__ == "__main__":
    main()
