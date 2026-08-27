"""
Lets a published flow be called from outside the hub entirely - a website,
a script, another app - without a logged-in session. Deliberately a
separate router from flow_routes.py: this one takes no session dependency
at all, only an API key, so a public flow can never accidentally also
accept (or require) a browser session.

A published flow runs as its owner - there's no "whoever's logged in" to
fall back to for an external caller, so Gmail/Drive nodes act as the person
who published it, the same as a scheduled run already does.
"""
from fastapi import APIRouter, Header, HTTPException
import json

from . import db, flow_engine, security
from .models import FlowRunRequest, FlowRunResponse

router = APIRouter(prefix="/public/flows", tags=["public"])


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
