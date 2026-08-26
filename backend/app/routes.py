import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile

from . import config, db, embeddings, ingest, loaders, security, vector_store
from .auth import get_current_user
from .models import (
    AdminPasswordResetRequest,
    ChunkResult,
    DocumentOut,
    ExtractedTextOut,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    QueryRequest,
    QueryResponse,
    UpdateEmailRequest,
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


@router.patch("/me/email")
def update_my_email(body: UpdateEmailRequest, user: dict = Depends(get_current_user)):
    email = (body.email or "").strip() or None
    if email is not None and ("@" not in email or "." not in email.split("@")[-1]):
        raise HTTPException(400, "That doesn't look like a valid email address")
    db.set_user_email(user["id"], email)
    return {"email": email}


@router.get("/users")
def list_team(user: dict = Depends(get_current_user)):
    return [_user_out(u) for u in db.list_users()]


@router.patch("/users/{user_id}/role")
def set_role(user_id: str, role: str, admin: dict = Depends(get_current_user)):
    if admin["role"] != "admin":
        raise HTTPException(403, "Only a hub admin can change roles")
    if role not in ("admin", "member"):
        raise HTTPException(400, "role must be 'admin' or 'member'")
    target = db.get_user(user_id)
    if target is None:
        raise HTTPException(404, "No such user")
    if role == "member" and _would_remove_last_admin(user_id, target["role"]):
        raise HTTPException(400, "Can't remove the only admin - promote someone else first")
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
    db.invalidate_password_reset_tokens_for_user(user_id)  # a stale email link shouldn't override this
    return {"reset": True}


@router.post("/extract-text", response_model=ExtractedTextOut)
async def extract_text(file: UploadFile, user: dict = Depends(get_current_user)):
    """Pulls the plain text out of an uploaded PDF/DOCX/CSV/TXT/MD - for
    feeding a whole document into a flow or a chat message as one-off input
    (a meeting transcript to summarize, say), not for building a searchable
    Knowledge base. Nothing is saved - the file is read, extracted, and
    discarded in the same request."""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in config.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{suffix}'. Allowed: {sorted(config.ALLOWED_EXTENSIONS)}")

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > config.MAX_UPLOAD_MB:
        raise HTTPException(400, f"File is {size_mb:.1f}MB, limit is {config.MAX_UPLOAD_MB}MB")

    with tempfile.NamedTemporaryFile(suffix=suffix) as tmp:
        tmp.write(contents)
        tmp.flush()
        try:
            text = loaders.load_text(Path(tmp.name))
        except Exception as exc:  # noqa: BLE001 - a bad/corrupt file should be a clean 400, not a 500
            raise HTTPException(400, f"Couldn't read this file: {exc}")

    if not text.strip():
        raise HTTPException(400, "No extractable text found in this file")
    return ExtractedTextOut(filename=file.filename, content=text)


def _would_remove_last_admin(user_id: str, target_role: str) -> bool:
    if target_role != "admin":
        return False
    remaining = [u for u in db.list_users() if u["role"] == "admin" and u["id"] != user_id]
    return len(remaining) == 0


@router.delete("/users/{user_id}")
def delete_user(user_id: str, admin: dict = Depends(get_current_user)):
    if admin["role"] != "admin":
        raise HTTPException(403, "Only a hub admin can remove team members")
    if user_id == admin["id"]:
        raise HTTPException(400, "You can't remove your own account this way")
    target = db.get_user(user_id)
    if target is None:
        raise HTTPException(404, "No such user")
    if _would_remove_last_admin(user_id, target["role"]):
        raise HTTPException(400, "Can't remove the only admin - promote someone else first")
    # their shared/private flows and knowledge bases transfer to whoever's
    # removing them, rather than vanishing or leaving a dangling owner
    db.reassign_user_data(user_id, admin["id"])
    db.delete_user(user_id)
    return {"deleted": user_id}


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
