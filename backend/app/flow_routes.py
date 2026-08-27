import json

from fastapi import APIRouter, Depends, HTTPException

from . import db, flow_engine, security
from .auth import get_current_user
from .models import (
    FlowCreate,
    FlowGraph,
    FlowOut,
    FlowPublishResponse,
    FlowRunRequest,
    FlowRunResponse,
    FlowSummaryOut,
    FlowUpdate,
)

router = APIRouter(prefix="/flows", tags=["flows"])


def _flow_out(flow) -> FlowOut:
    graph = json.loads(flow["graph_json"])
    data = dict(flow)
    published = bool(data.pop("api_key_hash", None))  # never pass the hash into the response model
    return FlowOut(**data, graph=graph, published=published)


def _flow_summary(flow) -> FlowSummaryOut:
    graph = json.loads(flow["graph_json"])
    return FlowSummaryOut(**dict(flow), node_count=len(graph.get("nodes", [])))


def _require_flow_access(flow_id: str, user: dict):
    flow = db.get_flow(flow_id)
    if flow is None:
        raise HTTPException(404, "Flow not found")
    is_admin = user["role"] == "admin"
    if not db.user_can_access_flow(flow, user["id"], is_admin=is_admin):
        raise HTTPException(403, "This flow is private to another team member")
    return flow


def _require_flow_owner(flow_id: str, user: dict):
    flow = _require_flow_access(flow_id, user)
    if flow["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "Only the owner or a hub admin can do this")
    return flow


@router.post("", response_model=FlowOut)
def create_flow(body: FlowCreate, user: dict = Depends(get_current_user)):
    flow_id = db.create_flow(body.name, body.description, user["id"], body.visibility)
    return _flow_out(db.get_flow(flow_id))


@router.get("", response_model=list[FlowSummaryOut])
def list_flows(user: dict = Depends(get_current_user)):
    is_admin = user["role"] == "admin"
    return [_flow_summary(f) for f in db.list_flows_for_user(user["id"], is_admin=is_admin)]


@router.get("/{flow_id}", response_model=FlowOut)
def get_flow(flow_id: str, user: dict = Depends(get_current_user)):
    flow = _require_flow_access(flow_id, user)
    return _flow_out(flow)


@router.put("/{flow_id}", response_model=FlowOut)
def update_flow(flow_id: str, body: FlowUpdate, user: dict = Depends(get_current_user)):
    _require_flow_access(flow_id, user)
    graph_json = json.dumps(body.graph.model_dump()) if body.graph is not None else None
    db.update_flow(
        flow_id, name=body.name, description=body.description,
        visibility=body.visibility, graph_json=graph_json,
    )
    return _flow_out(db.get_flow(flow_id))


@router.delete("/{flow_id}")
def delete_flow(flow_id: str, user: dict = Depends(get_current_user)):
    flow = _require_flow_access(flow_id, user)
    if flow["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "Only the owner or a hub admin can delete this flow")
    db.delete_flow(flow_id)
    return {"deleted": flow_id}


@router.post("/{flow_id}/run", response_model=FlowRunResponse)
def run_flow(flow_id: str, body: FlowRunRequest, user: dict = Depends(get_current_user)):
    flow = _require_flow_access(flow_id, user)
    graph = json.loads(flow["graph_json"])
    try:
        result = flow_engine.run_flow(graph, body.input, user["id"], flow_id=flow_id)
    except flow_engine.FlowError as exc:
        raise HTTPException(400, {"node_id": exc.node_id, "message": str(exc)})
    return FlowRunResponse(**result)


@router.post("/{flow_id}/publish", response_model=FlowPublishResponse)
def publish_flow(flow_id: str, user: dict = Depends(get_current_user)):
    """Generates a new API key for this flow (replacing any existing one -
    only one live key per flow, so publishing again is how you rotate it).
    The raw key is only ever shown here, once - only its hash is stored."""
    _require_flow_owner(flow_id, user)
    api_key = security.new_api_key()
    db.set_flow_api_key_hash(flow_id, security.hash_api_key(api_key))
    return FlowPublishResponse(api_key=api_key, run_url=f"/api/public/flows/{flow_id}/run")


@router.delete("/{flow_id}/publish")
def unpublish_flow(flow_id: str, user: dict = Depends(get_current_user)):
    _require_flow_owner(flow_id, user)
    db.set_flow_api_key_hash(flow_id, None)
    return {"published": False}
