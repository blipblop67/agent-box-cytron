"""
Session-based auth. A login/register call (see auth_routes.py) verifies a
password and returns an opaque session token; every other request presents
that token and this file is what turns it back into a user.

Every other route module depends on get_current_user and only ever reads
the {id, name, role} dict it returns - swapping how a session is
established (this file) never has to touch any of them.
"""
import re

from fastapi import Header, HTTPException

from . import db


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "user"


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    token = extract_bearer_token(authorization)
    if token is None:
        raise HTTPException(status_code=401, detail="Not logged in")

    session = db.get_session(token)
    if session is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid - please log in again")

    user = db.get_user(session["user_id"])
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid - please log in again")

    return {"id": user["id"], "name": user["name"], "role": user["role"]}


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    return authorization.removeprefix("Bearer ").strip() or None
