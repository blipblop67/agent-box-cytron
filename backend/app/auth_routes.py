"""
Session lifecycle. authenticate() deliberately combines login and
registration behind one call - the frontend just asks for a name and a
password, same as it always asked for just a name; the backend decides
whether that's a new account, a login, or (for anyone who used the hub
before passwords existed) claiming their existing nameonly account.
"""
from fastapi import APIRouter, Depends, Header, HTTPException

from . import auth, db, security
from .auth import get_current_user
from .models import AuthRequest, AuthResponse, ChangePasswordRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/authenticate", response_model=AuthResponse)
def authenticate(body: AuthRequest):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name can't be empty")
    if len(body.password) < security.MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {security.MIN_PASSWORD_LENGTH} characters")
    if len(body.password) > 128:
        raise HTTPException(400, "Password is too long")

    user_id = auth.slugify(name)
    if security.is_locked_out(user_id):
        raise HTTPException(429, "Too many failed attempts on this name - wait a few minutes and try again")

    existing = db.get_user(user_id)

    if existing is None:
        # brand new account
        db.create_user(user_id, name, security.hash_password(body.password))
        user = db.get_user(user_id)
    elif existing["password_hash"] is None:
        # a name from before passwords existed - claim it, keep its id/role/history
        db.set_user_password(user_id, security.hash_password(body.password))
        user = db.get_user(user_id)
    else:
        if not security.verify_password(body.password, existing["password_hash"]):
            security.record_failed_attempt(user_id)
            raise HTTPException(401, "Incorrect password for this name")
        user = existing

    security.clear_attempts(user_id)
    token = security.new_session_token()
    db.create_session(token, user["id"], security.SESSION_TTL_SECONDS)
    return AuthResponse(token=token, user={"id": user["id"], "name": user["name"], "role": user["role"]})


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)):
    token = auth.extract_bearer_token(authorization)
    if token:
        db.delete_session(token)
    return {"logged_out": True}


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    row = db.get_user(user["id"])
    if not security.verify_password(body.current_password, row["password_hash"]):
        raise HTTPException(401, "Current password is incorrect")
    if len(body.new_password) < security.MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {security.MIN_PASSWORD_LENGTH} characters")
    db.set_user_password(user["id"], security.hash_password(body.new_password))
    db.delete_all_sessions_for_user(user["id"])
    return {"changed": True}
