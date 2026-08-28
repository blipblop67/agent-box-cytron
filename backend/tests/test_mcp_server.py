"""
Proves a published flow's MCP server endpoint (/public/flows/{id}/mcp)
speaks correct JSON-RPC 2.0 - the full handshake (initialize, the
notifications/initialized notification, tools/list, tools/call), auth via
the same API key the REST publish endpoint already uses (just presented
as a Bearer token instead of X-API-Key), and that a flow failure surfaces
as a tool-level error (isError: true) rather than a protocol-level one,
since the call itself succeeded even if the flow didn't.
Run with: python3 tests/test_mcp_server.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-mcpserver-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")

    flow = client.post("/api/flows", headers=headers, json={
        "name": "Echo Agent", "description": "Repeats back whatever it's given",
    }).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "out", "type": "output", "position": {"x": 300, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})
    publish_result = client.post(f"/api/flows/{flow['id']}/publish", headers=headers).json()
    api_key = publish_result["api_key"]

    mcp_url = f"/api/public/flows/{flow['id']}/mcp"

    # --- no auth at all ---
    no_auth = client.post(mcp_url, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert no_auth.status_code == 401
    print("[ok] no Authorization header is rejected")

    # --- wrong key ---
    wrong_key = client.post(mcp_url, headers={"Authorization": "Bearer not-the-real-key"},
                             json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert wrong_key.status_code == 401
    print("[ok] the wrong API key (as a Bearer token) is rejected")

    auth_header = {"Authorization": f"Bearer {api_key}"}

    # --- initialize ---
    init_resp = client.post(mcp_url, headers=auth_header, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {},
    })
    assert init_resp.status_code == 200
    init_body = init_resp.json()
    assert init_body["jsonrpc"] == "2.0" and init_body["id"] == 1
    assert init_body["result"]["serverInfo"]["name"] == "Echo Agent"
    assert "tools" in init_body["result"]["capabilities"]
    print(f"[ok] initialize handshake succeeded, server identifies itself as: {init_body['result']['serverInfo']['name']!r}")

    # --- the initialized notification - no id, no response body expected ---
    notify_resp = client.post(mcp_url, headers=auth_header, json={
        "jsonrpc": "2.0", "method": "notifications/initialized", "params": {},
    })
    assert notify_resp.status_code == 202
    print("[ok] the notifications/initialized notification is acknowledged with 202, no body")

    # --- tools/list - exactly one tool, with a real schema ---
    list_resp = client.post(mcp_url, headers=auth_header, json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
    })
    assert list_resp.status_code == 200
    tools = list_resp.json()["result"]["tools"]
    assert len(tools) == 1
    assert tools[0]["name"] == "run_flow"
    assert tools[0]["description"] == "Repeats back whatever it's given"
    assert tools[0]["inputSchema"]["required"] == ["input"]
    print(f"[ok] tools/list returned exactly one tool: {tools[0]['name']!r} - {tools[0]['description']!r}")

    # --- tools/call - actually runs the flow ---
    call_resp = client.post(mcp_url, headers=auth_header, json={
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "run_flow", "arguments": {"input": "hello from an MCP client"}},
    })
    assert call_resp.status_code == 200
    call_result = call_resp.json()["result"]
    assert call_result["isError"] is False
    assert call_result["content"][0]["text"] == "hello from an MCP client"
    print(f"[ok] tools/call actually ran the flow: {call_result['content'][0]['text']!r}")

    # --- calling an unknown tool name gives a proper JSON-RPC error, not a crash ---
    bad_tool_resp = client.post(mcp_url, headers=auth_header, json={
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "not_a_real_tool", "arguments": {}},
    })
    assert bad_tool_resp.status_code == 200  # JSON-RPC errors are still HTTP 200 - the error is in the body
    assert "error" in bad_tool_resp.json()
    assert bad_tool_resp.json()["error"]["code"] == -32602
    print("[ok] calling an unknown tool name gives a JSON-RPC error (-32602), not a crash")

    # --- an unknown method gives -32601 ---
    bad_method_resp = client.post(mcp_url, headers=auth_header, json={
        "jsonrpc": "2.0", "id": 5, "method": "resources/list", "params": {},
    })
    assert bad_method_resp.json()["error"]["code"] == -32601
    print("[ok] an unsupported method gives a proper -32601 'method not found' error")

    # --- a flow that fails surfaces as a TOOL-level error (isError: true), not a
    # protocol-level failure - the MCP call itself succeeded, the flow didn't ---
    broken_flow = client.post("/api/flows", headers=headers, json={"name": "Broken Flow"}).json()
    broken_graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "calc", "type": "calculator", "position": {"x": 200, "y": 0}, "data": {}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "calc"}, {"id": "e2", "source": "calc", "target": "out"}],
    }
    client.put(f"/api/flows/{broken_flow['id']}", headers=headers, json={"graph": broken_graph})
    broken_publish = client.post(f"/api/flows/{broken_flow['id']}/publish", headers=headers).json()
    broken_mcp_url = f"/api/public/flows/{broken_flow['id']}/mcp"
    broken_auth = {"Authorization": f"Bearer {broken_publish['api_key']}"}

    broken_call = client.post(broken_mcp_url, headers=broken_auth, json={
        "jsonrpc": "2.0", "id": 6, "method": "tools/call",
        "params": {"name": "run_flow", "arguments": {"input": "not a valid math expression!!"}},
    })
    assert broken_call.status_code == 200
    broken_result = broken_call.json()["result"]
    assert broken_result["isError"] is True
    print(f"[ok] a flow failure surfaces as a tool-level error (isError: true): {broken_result['content'][0]['text'][:60]}...")

    # --- the exact same flow is independently reachable via the REST publish
    # endpoint with the SAME key, proving both are just two doors into the same
    # thing, not two separate systems ---
    rest_result = client.post(f"/api/public/flows/{flow['id']}/run", headers={"X-API-Key": api_key},
                               json={"input": "same flow, the other door"})
    assert rest_result.status_code == 200
    assert rest_result.json()["output"] == "same flow, the other door"
    print("[ok] the exact same flow and API key also work through the plain REST publish endpoint")

    print("\nAll MCP server smoke tests passed.")


if __name__ == "__main__":
    main()
