"""
Lets a published flow be called from outside the hub entirely - a website,
a script, another app - without a logged-in session. Deliberately a
separate router from flow_routes.py: this one takes no session dependency
at all, only an API key, so a public flow can never accidentally also
accept (or require) a browser session.

A published flow runs as its owner - there's no "whoever's logged in" to
fall back to for an external caller, so Gmail/Drive nodes act as the person
who published it, the same as a scheduled run already does.

Two ways in, same flow, same API key: a plain REST endpoint (below) for
anything that just wants to POST some text and get text back, and an MCP
endpoint (mcp_client.py's exact counterpart - a real MCP client, including
another Agent Hub flow's own MCP node, can call this flow as a tool) for
anything that speaks MCP already. Neither is "the real one" - they're the
same underlying flow run, reached two different ways.
"""
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
import json

from . import db, flow_engine, security
from .models import FlowRunRequest, FlowRunResponse

router = APIRouter(prefix="/public/flows", tags=["public"])

MCP_PROTOCOL_VERSION = "2024-11-05"
TOOL_NAME = "run_flow"


@router.post("/{flow_id}/run", response_model=FlowRunResponse)
def run_published_flow(flow_id: str, body: FlowRunRequest, x_api_key: str | None = Header(default=None)):
    if not x_api_key:
        raise HTTPException(401, "Missing X-API-Key header")
    flow = db.get_flow(flow_id)
    if flow is None or not flow["api_key_hash"]:
        raise HTTPException(404, "No published flow here")
    if security.hash_api_key(x_api_key) != flow["api_key_hash"]:
        raise HTTPException(401, "Invalid API key")

    graph = json.loads(flow["graph_json"])
    try:
        result = flow_engine.run_flow(graph, body.input, flow["owner_id"], flow_id=flow_id)
    except flow_engine.FlowError as exc:
        raise HTTPException(400, {"node_id": exc.node_id, "message": str(exc)})
    return FlowRunResponse(**result)


def _require_published_flow(flow_id: str, authorization: str | None):
    """Same check as the REST endpoint above, but reading the API key from
    an `Authorization: Bearer <key>` header instead of X-API-Key - the
    header shape a real MCP client (including this hub's own MCP node)
    actually sends, rather than something MCP-specific to remember."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing or malformed Authorization header - expected 'Bearer <api-key>'")
    api_key = authorization.split(" ", 1)[1].strip()
    flow = db.get_flow(flow_id)
    if flow is None or not flow["api_key_hash"]:
        raise HTTPException(404, "No published flow here")
    if security.hash_api_key(api_key) != flow["api_key_hash"]:
        raise HTTPException(401, "Invalid API key")
    return flow


def _jsonrpc_error(request_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _jsonrpc_result(request_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


@router.post("/{flow_id}/mcp")
async def mcp_server(flow_id: str, request: Request, authorization: str | None = Header(default=None)):
    """A published flow, reachable as an MCP server: one tool
    (`run_flow`) that runs this exact flow, with an inputSchema of just
    {"input": "..."} since that's all a flow ever takes. Real MCP clients
    (Claude Desktop, Claude.ai, another Agent Hub flow's MCP node) speak
    JSON-RPC 2.0 over a single POST like this one - see mcp_client.py for
    the client side of the exact same protocol."""
    flow = _require_published_flow(flow_id, authorization)

    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError):
        return JSONResponse(_jsonrpc_error(None, -32700, "Parse error - request body wasn't valid JSON"), status_code=400)

    method = body.get("method")
    request_id = body.get("id")
    params = body.get("params") or {}

    if method == "initialize":
        return _jsonrpc_result(request_id, {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": flow["name"], "version": "1.0"},
        })

    if method == "notifications/initialized":
        # a notification - no "id", no response body expected, just acknowledge receipt
        return Response(status_code=202)

    if method == "tools/list":
        return _jsonrpc_result(request_id, {"tools": [{
            "name": TOOL_NAME,
            "description": flow["description"] or f"Runs the '{flow['name']}' flow",
            "inputSchema": {
                "type": "object",
                "properties": {"input": {"type": "string", "description": "The message or task to send to this flow"}},
                "required": ["input"],
            },
        }]})

    if method == "tools/call":
        tool_name = params.get("name")
        if tool_name != TOOL_NAME:
            return _jsonrpc_error(request_id, -32602, f"Unknown tool '{tool_name}' - this server only offers '{TOOL_NAME}'")
        arguments = params.get("arguments") or {}
        flow_input = arguments.get("input", "")

        graph = json.loads(flow["graph_json"])
        try:
            result = flow_engine.run_flow(graph, flow_input, flow["owner_id"], flow_id=flow_id)
        except flow_engine.FlowError as exc:
            # a failure *running the flow* is a tool-level error, not a protocol-level
            # one - the call itself succeeded, the underlying operation didn't
            return _jsonrpc_result(request_id, {
                "content": [{"type": "text", "text": str(exc)}],
                "isError": True,
            })
        return _jsonrpc_result(request_id, {
            "content": [{"type": "text", "text": result["output"]}],
            "isError": False,
        })

    return _jsonrpc_error(request_id, -32601, f"Method not found: '{method}'")
