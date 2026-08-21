import json

from fastapi import APIRouter, Depends, HTTPException

from . import db, templates as template_lib
from .auth import get_current_user
from .flow_routes import _flow_out
from .models import FlowOut, TemplateSummary, TemplateUse

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateSummary])
def list_templates():
    return template_lib.list_templates()


@router.post("/{template_id}/use", response_model=FlowOut)
def use_template(template_id: str, body: TemplateUse, user: dict = Depends(get_current_user)):
    template = template_lib.get_template(template_id)
    if template is None:
        raise HTTPException(404, "No such template")
    name = body.name or template["name"]
    flow_id = db.create_flow(name, template["description"], user["id"], "shared")
    db.update_flow(flow_id, graph_json=json.dumps(template["graph"]))
    return _flow_out(db.get_flow(flow_id))
