"""
Proves the MCP node actually works inside a real flow run, and that the
/mcp/list-tools endpoint the config panel's picker depends on works too -
both against a mocked MCP server (see test_mcp_client.py for the client
transport-level tests this builds on).
Run with: python3 tests/test_mcp_node.py
"""
import json as json_module
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-mcpnode-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


class FakeResponse:
    def __init__(self, text_data="", status_code=200, headers=None):
        self.text = text_data
        self.status_code = status_code
        self.headers = {**(headers or {}), "content-type": "application/json"}

    def json(self):
        return json_module.loads(self.text)


def fake_mcp_server(url, json=None, headers=None, **kwargs):
    method = json.get("method")
    if method == "initialize":
        return FakeResponse(json_module.dumps({"jsonrpc": "2.0", "id": json["id"], "result": {}}),
                             headers={"Mcp-Session-Id": "sess-1"})
    if method == "notifications/initialized":
        return FakeResponse(status_code=202)
    if method == "tools/list":
        return FakeResponse(json_module.dumps({"jsonrpc": "2.0", "id": json["id"], "result": {"tools": [
            {"name": "get_weather", "description": "Get current weather", "inputSchema": {
                "type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"],
            }},
            {"name": "get_forecast", "description": "Get a 5-day forecast", "inputSchema": {}},
        ]}}))
    if method == "tools/call":
        assert json["params"]["name"] == "get_weather"
        assert json["params"]["arguments"] == {"city": "Penang"}
        return FakeResponse(json_module.dumps({"jsonrpc": "2.0", "id": json["id"], "result": {
            "content": [{"type": "text", "text": "Sunny, 30C in Penang"}], "isError": False,
        }}))
    raise AssertionError(f"unexpected method {method}")


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")

    # --- the config panel's "list tools" picker ---
    with patch("httpx.post", side_effect=fake_mcp_server):
        list_result = client.post("/api/mcp/list-tools", headers=headers, json={
            "server_url": "https://weather-mcp.test/mcp",
        })
    assert list_result.status_code == 200
    tools = list_result.json()["tools"]
    assert {t["name"] for t in tools} == {"get_weather", "get_forecast"}
    print(f"[ok] /mcp/list-tools returned {len(tools)} tools for the config panel picker")

    # --- an unreachable server gives a clean 400, not a 500 ---
    def fake_unreachable(url, json=None, headers=None, **kwargs):
        import httpx
        raise httpx.ConnectError("connection refused")

    with patch("httpx.post", side_effect=fake_unreachable):
        bad_result = client.post("/api/mcp/list-tools", headers=headers, json={
            "server_url": "https://unreachable.test/mcp",
        })
    assert bad_result.status_code == 400
    print("[ok] an unreachable server gives a clean 400 with a real message, not a raw 500")

    # --- THE ACTUAL POINT: an MCP node works inside a real flow, with an upstream
    # LLM node's JSON output correctly parsed into the tool's arguments ---
    flow = client.post("/api/flows", headers=headers, json={"name": "Weather Checker"}).json()
    graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "mcp", "type": "mcp", "position": {"x": 200, "y": 0}, "data": {
                "server_url": "https://weather-mcp.test/mcp", "tool_name": "get_weather",
            }},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "mcp"}, {"id": "e2", "source": "mcp", "target": "out"}],
    }
    client.put(f"/api/flows/{flow['id']}", headers=headers, json={"graph": graph})

    with patch("httpx.post", side_effect=fake_mcp_server):
        result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={
            "input": '{"city": "Penang"}',  # the shape an upstream LLM node would be prompted to produce
        })
    assert result.status_code == 200, result.text
    assert result.json()["output"] == "Sunny, 30C in Penang"
    print(f"[ok] a real flow with an MCP node ran end to end: {result.json()['output']!r}")

    # --- non-JSON input falls back to a single {"input": ...} argument, for
    # simple tools that just take one string, without forcing a JSON-writing LLM step ---
    def fake_single_arg_tool(url, json=None, headers=None, **kwargs):
        method = json.get("method")
        if method == "initialize":
            return FakeResponse(json_module.dumps({"jsonrpc": "2.0", "id": json["id"], "result": {}}))
        if method == "notifications/initialized":
            return FakeResponse(status_code=202)
        if method == "tools/call":
            assert json["params"]["arguments"] == {"input": "just plain text, not JSON"}
            return FakeResponse(json_module.dumps({"jsonrpc": "2.0", "id": json["id"], "result": {
                "content": [{"type": "text", "text": "handled plain text ok"}], "isError": False,
            }}))
        raise AssertionError

    plain_flow = client.post("/api/flows", headers=headers, json={"name": "Plain Text Tool"}).json()
    plain_graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "mcp", "type": "mcp", "position": {"x": 200, "y": 0}, "data": {
                "server_url": "https://simple-mcp.test/mcp", "tool_name": "echo",
            }},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "mcp"}, {"id": "e2", "source": "mcp", "target": "out"}],
    }
    client.put(f"/api/flows/{plain_flow['id']}", headers=headers, json={"graph": plain_graph})
    with patch("httpx.post", side_effect=fake_single_arg_tool):
        plain_result = client.post(f"/api/flows/{plain_flow['id']}/run", headers=headers, json={
            "input": "just plain text, not JSON",
        })
    assert plain_result.status_code == 200, plain_result.text
    assert plain_result.json()["output"] == "handled plain text ok"
    print("[ok] non-JSON input is wrapped as {'input': ...} for simple single-argument tools")

    # --- a missing server URL / tool name give clear errors, not crashes ---
    broken_flow = client.post("/api/flows", headers=headers, json={"name": "Broken MCP node"}).json()
    broken_graph = {
        "nodes": [
            {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
            {"id": "mcp", "type": "mcp", "position": {"x": 200, "y": 0}, "data": {}},
            {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
        ],
        "edges": [{"id": "e1", "source": "in", "target": "mcp"}, {"id": "e2", "source": "mcp", "target": "out"}],
    }
    client.put(f"/api/flows/{broken_flow['id']}", headers=headers, json={"graph": broken_graph})
    broken_result = client.post(f"/api/flows/{broken_flow['id']}/run", headers=headers, json={"input": "x"})
    assert broken_result.status_code == 400
    assert "server URL" in str(broken_result.json())
    print("[ok] an MCP node with no server URL configured gives a clear error")

    print("\nAll MCP node smoke tests passed.")


if __name__ == "__main__":
    main()
