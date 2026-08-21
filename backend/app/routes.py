from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile

from . import config, db, embeddings, ingest, security, vector_store
from .auth import get_current_user
from .models import (
    AdminPasswordResetRequest,
    ChunkResult,
    DocumentOut,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    QueryRequest,
    QueryResponse,
)

router = APIRouter()


def _kb_out(kb) -> KnowledgeBaseOut:
    doc_count = len(db.list_documents(kb["id"]))
    return KnowledgeBaseOut(**dict(kb), document_count=doc_count)


def _require_kb_access(kb_id: str, user: dict):
    kb = db.get_kb(kb_id)
    if kb is None:
        raise HTTPException(404, "Knowledge base not found")
    is_admin = user["role"] == "admin"
    if not db.user_can_access_kb(kb, user["id"], is_admin=is_admin):
        raise HTTPException(403, "This knowledge base is private to another team member")
    return kb


def _user_out(row) -> dict:
    # never return password_hash - list_users()/get_user() pull every column,
    # this is the one place that decides what's safe to hand back over the API
    return {"id": row["id"], "name": row["name"], "role": row["role"], "created_at": row["created_at"]}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user


@router.get("/users")
def list_team(user: dict = Depends(get_current_user)):
    return [_user_out(u) for u in db.list_users()]


@router.patch("/users/{user_id}/role")
def set_role(user_id: str, role: str, admin: dict = Depends(get_current_user)):
    if admin["role"] != "admin":
        raise HTTPException(403, "Only a hub admin can change roles")
    if role not in ("admin", "member"):
        raise HTTPException(400, "role must be 'admin' or 'member'")
    if db.get_user(user_id) is None:
        raise HTTPException(404, "No such user")
    db.set_user_role(user_id, role)
    return {"id": user_id, "role": role}


@router.patch("/users/{user_id}/password")
def admin_reset_password(user_id: str, body: AdminPasswordResetRequest, admin: dict = Depends(get_current_user)):
    if admin["role"] != "admin":
        raise HTTPException(403, "Only a hub admin can reset another user's password")
    if db.get_user(user_id) is None:
        raise HTTPException(404, "No such user")
    if len(body.new_password) < security.MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {security.MIN_PASSWORD_LENGTH} characters")
    db.set_user_password(user_id, security.hash_password(body.new_password))
    db.delete_all_sessions_for_user(user_id)  # they'll need to log in again with the new password
    return {"reset": True}


@router.post("/knowledge-bases", response_model=KnowledgeBaseOut)
def create_knowledge_base(body: KnowledgeBaseCreate, user: dict = Depends(get_current_user)):
    kb_id = db.create_kb(body.name, body.description, user["id"], body.visibility)
    return _kb_out(db.get_kb(kb_id))


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseOut])
def list_knowledge_bases(user: dict = Depends(get_current_user)):
    is_admin = user["role"] == "admin"
    return [_kb_out(kb) for kb in db.list_kbs_for_user(user["id"], is_admin=is_admin)]


@router.delete("/knowledge-bases/{kb_id}")
def delete_knowledge_base(kb_id: str, user: dict = Depends(get_current_user)):
    kb = _require_kb_access(kb_id, user)
    if kb["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "Only the owner or a hub admin can delete this knowledge base")
    vector_store.delete_collection(kb_id)
    db.delete_kb(kb_id)
    return {"deleted": kb_id}


@router.post("/knowledge-bases/{kb_id}/documents", response_model=DocumentOut)
async def upload_document(
    kb_id: str,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    _require_kb_access(kb_id, user)

    suffix = Path(file.filename).suffix.lower()
    if suffix not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{suffix}'. Allowed: {sorted(config.ALLOWED_EXTENSIONS)}")

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > config.MAX_UPLOAD_MB:
        raise HTTPException(400, f"File is {size_mb:.1f}MB, limit is {config.MAX_UPLOAD_MB}MB")

    doc_id = db.create_document(kb_id, file.filename, file.content_type, len(contents), user["id"])

    kb_dir = config.UPLOAD_DIR / kb_id
    kb_dir.mkdir(parents=True, exist_ok=True)
    dest = kb_dir / f"{doc_id}{suffix}"
    dest.write_bytes(contents)

    background_tasks.add_task(ingest.ingest_document, doc_id, kb_id, dest)

    return DocumentOut(**dict(db.get_document(doc_id)))


@router.get("/knowledge-bases/{kb_id}/documents", response_model=list[DocumentOut])
def list_documents(kb_id: str, user: dict = Depends(get_current_user)):
    _require_kb_access(kb_id, user)
    return [DocumentOut(**dict(d)) for d in db.list_documents(kb_id)]


@router.delete("/knowledge-bases/{kb_id}/documents/{doc_id}")
def delete_document(kb_id: str, doc_id: str, user: dict = Depends(get_current_user)):
    _require_kb_access(kb_id, user)
    vector_store.delete_document_chunks(kb_id, doc_id)
    db.delete_document(doc_id)
    return {"deleted": doc_id}


@router.post("/knowledge-bases/{kb_id}/query", response_model=QueryResponse)
def query_knowledge_base(kb_id: str, body: QueryRequest, user: dict = Depends(get_current_user)):
    """This is what a 'Knowledge base' node in the flow builder calls at agent
    run-time - text in, relevant chunks out, ready to splice into a prompt."""
    _require_kb_access(kb_id, user)
    top_k = body.top_k or config.DEFAULT_TOP_K

    provider = embeddings.get_embedding_provider()
    [query_vector] = provider.embed([body.query])

    raw_results = vector_store.query(kb_id, query_vector, top_k)
    results = [ChunkResult(**r) for r in raw_results]
    return QueryResponse(kb_id=kb_id, query=body.query, results=results)
