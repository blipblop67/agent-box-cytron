"""
The one endpoint the MCP node's config panel needs directly: given a
server URL (and optional auth token), list what tools it offers, so
someone building a flow can pick one by name instead of typing it blind.
The actual tool *call* during a flow run goes through flow_engine.py
directly, not this router - this exists purely to support the picker UI.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from . import mcp_client
from .auth import get_current_user

router = APIRouter(prefix="/mcp", tags=["mcp"])


class ListToolsRequest(BaseModel):
    server_url: str
    auth_token: str | None = None


@router.post("/list-tools")
def list_tools(body: ListToolsRequest, user: dict = Depends(get_current_user)):
    try:
        return {"tools": mcp_client.list_tools(body.server_url, body.auth_token)}
    except mcp_client.McpError as exc:
        raise HTTPException(400, str(exc))
