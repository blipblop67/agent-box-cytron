"""
Exercises the hand-rolled MCP client (mcp_client.py) against a mocked MCP
server, without touching a real one - covers the two response transports
real-world MCP servers actually use (plain JSON, and Streamable HTTP's
SSE mode), session ID propagation across calls, and the three ways a
call can fail (tool-level error, server-level HTTP error, and a
connection failure) so each surfaces a clear McpError rather than a raw
exception leaking through.
Run with: python3 tests/test_mcp_client.py
"""
import json as json_module
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-mcpclient-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app import mcp_client  # noqa: E402


class FakeResponse:
    def __init__(self, text_data="", status_code=200, headers=None, content_type="application/json"):
        self.text = text_data
        self.status_code = status_code
        self.headers = {**(headers or {}), "content-type": content_type}

    def json(self):
        return json_module.loads(self.text)


def _sse_wrap(payload: dict) -> str:
    return f"event: message\ndata: {json_module.dumps(payload)}\n\n"


def main():
    # --- plain JSON transport: list_tools then call_tool, with session ID propagation ---
    def fake_json_mode(url, json=None, headers=None, **kwargs):
        method = json.get("method")
        if method == "initialize":
            return FakeResponse(
                json_module.dumps({"jsonrpc": "2.0", "id": json["id"], "result": {"protocolVersion": "2024-11-05"}}),
                headers={"Mcp-Session-Id": "sess-abc123"},
            )
        if method == "notifications/initialized":
            return FakeResponse(status_code=202)
        if method == "tools/list":
            assert headers.get("Mcp-Session-Id") == "sess-abc123"
            return FakeResponse(json_module.dumps({"jsonrpc": "2.0", "id": json["id"], "result": {"tools": [
                {"name": "get_weather", "description": "Get current weather for a city",
                 "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}}},
            ]}}))
        if method == "tools/call":
            assert json["params"]["name"] == "get_weather"
            assert json["params"]["arguments"] == {"city": "Kuala Lumpur"}
            return FakeResponse(json_module.dumps({"jsonrpc": "2.0", "id": json["id"], "result": {
                "content": [{"type": "text", "text": "Sunny, 31C in Kuala Lumpur"}], "isError": False,
            }}))
        raise AssertionError(f"unexpected method {method}")

    with patch("httpx.post", side_effect=fake_json_mode):
        tools = mcp_client.list_tools("https://example-mcp.test/mcp", auth_token="test-token")
        assert len(tools) == 1 and tools[0]["name"] == "get_weather"
        print(f"[ok] list_tools (plain JSON transport) found: {tools[0]['name']!r}")

        result = mcp_client.call_tool("https://example-mcp.test/mcp", "get_weather", {"city": "Kuala Lumpur"}, auth_token="test-token")
        assert result == "Sunny, 31C in Kuala Lumpur"
        print(f"[ok] call_tool (plain JSON transport) returned: {result!r}")

    # --- Streamable HTTP's SSE transport mode - a real MCP server can pick either ---
    def fake_sse_mode(url, json=None, headers=None, **kwargs):
        method = json.get("method")
        if method == "initialize":
            return FakeResponse(_sse_wrap({"jsonrpc": "2.0", "id": json["id"], "result": {}}),
                                 headers={"Mcp-Session-Id": "sess-sse-1"}, content_type="text/event-stream")
        if method == "notifications/initialized":
            return FakeResponse(status_code=202)
        if method == "tools/call":
            assert headers.get("Mcp-Session-Id") == "sess-sse-1"
            return FakeResponse(_sse_wrap({"jsonrpc": "2.0", "id": json["id"], "result": {
                "content": [{"type": "text", "text": "called via SSE transport"}], "isError": False,
            }}), content_type="text/event-stream")
        raise AssertionError(f"unexpected method {method}")

    with patch("httpx.post", side_effect=fake_sse_mode):
        result = mcp_client.call_tool("https://example-mcp.test/mcp", "some_tool", {"x": 1})
        assert result == "called via SSE transport"
        print(f"[ok] call_tool correctly parses the SSE transport mode too: {result!r}")

    # --- a tool-level error (isError: true) raises with the tool's own message ---
    def fake_tool_error(url, json=None, headers=None, **kwargs):
        method = json.get("method")
        if method == "initialize":
            return FakeResponse(json_module.dumps({"jsonrpc": "2.0", "id": json["id"], "result": {}}))
        if method == "notifications/initialized":
            return FakeResponse(status_code=202)
        if method == "tools/call":
            return FakeResponse(json_module.dumps({"jsonrpc": "2.0", "id": json["id"], "result": {
                "content": [{"type": "text", "text": "city not found"}], "isError": True,
            }}))
        raise AssertionError

    with patch("httpx.post", side_effect=fake_tool_error):
        try:
            mcp_client.call_tool("https://example-mcp.test/mcp", "get_weather", {"city": "Nowhereland"})
            raise AssertionError("should have raised McpError")
        except mcp_client.McpError as e:
            assert "city not found" in str(e)
            print(f"[ok] a tool-level error (isError: true) raises McpError with the tool's message: {e}")

    # --- a server-level HTTP error (not a tool error - the server itself is broken) ---
    def fake_http_error(url, json=None, headers=None, **kwargs):
        return FakeResponse(status_code=500, text_data="internal server error")

    with patch("httpx.post", side_effect=fake_http_error):
        try:
            mcp_client.list_tools("https://example-mcp.test/mcp")
            raise AssertionError("should have raised McpError")
        except mcp_client.McpError as e:
            assert "500" in str(e)
            print(f"[ok] a server-level HTTP error raises a clear McpError: {e}")

    # --- a connection failure (server unreachable entirely) ---
    def fake_conn_error(url, json=None, headers=None, **kwargs):
        raise httpx.ConnectError("connection refused")

    with patch("httpx.post", side_effect=fake_conn_error):
        try:
            mcp_client.list_tools("https://unreachable.test/mcp")
            raise AssertionError("should have raised McpError")
        except mcp_client.McpError as e:
            assert "reach" in str(e).lower()
            print(f"[ok] a connection failure raises a clear McpError, not a raw httpx exception: {e}")

    print("\nAll MCP client smoke tests passed.")


if __name__ == "__main__":
    main()
