"""
A minimal MCP (Model Context Protocol) client - talks to any MCP server
over the "Streamable HTTP" transport (a single POST endpoint speaking
JSON-RPC 2.0), which covers most real-world MCP servers reachable over a
URL. Hand-rolled rather than pulling in the official `mcp` Python SDK,
consistent with how every other external integration in this codebase
works (gmail_client.py, sheets_client.py, etc.) - plain REST/JSON-RPC is
simpler to read and debug than an SDK's abstraction, for the handful of
operations a flow node actually needs: discover a server's tools, call
one.

Deliberately doesn't implement the full spec - no resumable streams, no
client-side sampling, no resources/prompts, no persistent session reuse
across separate flow runs. Re-does the initialize handshake on every
call rather than caching a session, the same "simple over clever, worth
revisiting only if profiling ever says otherwise" trade this codebase
already makes for Google OAuth tokens and LLM provider credentials.
"""
import itertools
import json

import httpx

PROTOCOL_VERSION = "2024-11-05"
_id_counter = itertools.count(1)


class McpError(Exception):
    pass


def _next_id() -> int:
    return next(_id_counter)


def _post(server_url: str, headers: dict, payload: dict, session_id: str | None) -> tuple[dict | None, str | None]:
    """Sends one JSON-RPC message, returns (response_json_or_None, session_id).
    Handles both a plain JSON response and a Streamable-HTTP SSE response,
    since different MCP servers pick different ones for the same request."""
    req_headers = {
        **headers,
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        req_headers["Mcp-Session-Id"] = session_id

    try:
        resp = httpx.post(server_url, json=payload, headers=req_headers, timeout=30)
    except httpx.HTTPError as exc:
        raise McpError(f"Couldn't reach the MCP server: {exc}") from exc

    new_session_id = resp.headers.get("Mcp-Session-Id", session_id)

    if resp.status_code == 202:
        return None, new_session_id  # a notification - no response body expected

    if resp.status_code >= 400:
        raise McpError(f"MCP server returned {resp.status_code}: {resp.text[:300]}")

    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        data = _parse_sse_json(resp.text)
    else:
        try:
            data = resp.json()
        except ValueError as exc:
            raise McpError(f"MCP server didn't return valid JSON: {resp.text[:300]}") from exc

    if data and "error" in data:
        err = data["error"]
        raise McpError(f"MCP server error: {err.get('message', err) if isinstance(err, dict) else err}")

    return data, new_session_id


def _parse_sse_json(text: str) -> dict | None:
    """Streamable HTTP responses can arrive as an SSE stream rather than a
    plain JSON body - each `data: ` line is one JSON-RPC message; the last
    one is the actual reply to whatever request we just sent."""
    last = None
    for line in text.splitlines():
        if line.startswith("data:"):
            raw = line[len("data:"):].strip()
            if not raw:
                continue
            try:
                last = json.loads(raw)
            except json.JSONDecodeError:
                continue
    return last


def _initialize(server_url: str, headers: dict) -> str | None:
    """The MCP handshake - returns a session ID if the server issued one
    (via an Mcp-Session-Id response header, which many do)."""
    payload = {
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "agent-hub", "version": "1.0"},
        },
    }
    _, session_id = _post(server_url, headers, payload, None)
    # spec-compliant clients send this notification once initialize succeeds -
    # some servers require it before accepting tools/list or tools/call
    notify_payload = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    _post(server_url, headers, notify_payload, session_id)
    return session_id


def _auth_headers(auth_token: str | None) -> dict:
    return {"Authorization": f"Bearer {auth_token}"} if auth_token else {}


def list_tools(server_url: str, auth_token: str | None = None) -> list[dict]:
    headers = _auth_headers(auth_token)
    session_id = _initialize(server_url, headers)
    payload = {"jsonrpc": "2.0", "id": _next_id(), "method": "tools/list", "params": {}}
    data, _ = _post(server_url, headers, payload, session_id)
    if not data or "result" not in data:
        raise McpError("The server didn't return a tools list")
    return data["result"].get("tools", [])


def call_tool(server_url: str, tool_name: str, arguments: dict, auth_token: str | None = None) -> str:
    headers = _auth_headers(auth_token)
    session_id = _initialize(server_url, headers)
    payload = {
        "jsonrpc": "2.0", "id": _next_id(), "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    data, _ = _post(server_url, headers, payload, session_id)
    if not data or "result" not in data:
        raise McpError("The server didn't return a tool result")

    result = data["result"]
    content = result.get("content", [])
    texts = [c.get("text", "") for c in content if c.get("type") == "text"]
    text_output = "\n".join(texts) if texts else json.dumps(result)

    if result.get("isError"):
        raise McpError(f"The tool reported an error: {text_output or 'no details given'}")
    return text_output
