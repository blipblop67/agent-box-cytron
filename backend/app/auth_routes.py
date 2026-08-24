"""
Session lifecycle. authenticate() deliberately combines login and
registration behind one call - the frontend just asks for a name and a
password, same as it always asked for just a name; the backend decides
whether that's a new account, a login, or (for anyone who used the hub
before passwords existed) claiming their existing nameonly account.

forgot_password()/reset_password() are the email-based recovery path for
anyone who's set a recovery email on their Account page - see
email_sender.py and hub_settings.py's SMTP settings. Deliberately returns
the same generic response whether or not the account/email exists, so this
endpoint can't be used to discover which names are registered.
"""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from . import auth, db, email_sender, hub_settings, security
from .auth import get_current_user
from .models import (
    AuthRequest,
    AuthResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_FORGOT_PASSWORD_RESPONSE = {
    "message": "If that account has a recovery email set up, a reset link was just sent to it.",
}


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
    return AuthResponse(token=token, user={"id": user["id"], "name": user["name"], "role": user["role"], "email": user["email"]})


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
    db.invalidate_password_reset_tokens_for_user(user["id"])  # a stale email link shouldn't override this
    return {"changed": True}


@router.post("/forgot-password")
def forgot_password(request: Request, body: ForgotPasswordRequest):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name can't be empty")
    user_id = auth.slugify(name)

    # From here down, every exit path returns the exact same response -
    # whether the name doesn't exist, has no email, hit the rate limit, or
    # SMTP isn't configured - so none of that is discoverable from outside.
    if not security.can_request_password_reset(user_id):
        return GENERIC_FORGOT_PASSWORD_RESPONSE

    user = db.get_user(user_id)
    if user is None or not user["email"]:
        return GENERIC_FORGOT_PASSWORD_RESPONSE

    smtp_settings = hub_settings.get_smtp_settings()
    if not smtp_settings["configured"]:
        return GENERIC_FORGOT_PASSWORD_RESPONSE

    security.record_password_reset_request(user_id)

    raw_token = security.new_password_reset_token()
    db.create_password_reset_token(
        security.hash_password_reset_token(raw_token), user["id"], security.PASSWORD_RESET_TTL_SECONDS,
    )

    reset_url = f"{str(request.base_url).rstrip('/')}/reset-password?token={raw_token}"
    body_text = (
        f"Hi {user['name']},\n\n"
        f"Someone (hopefully you) asked to reset the password for your Agent Hub account.\n\n"
        f"Reset it here: {reset_url}\n\n"
        f"This link works once and expires in an hour. If you didn't request this, you can "
        f"ignore this email - your password hasn't been changed."
    )
    try:
        email_sender.send_email(user["email"], "Reset your Agent Hub password", body_text)
    except email_sender.EmailError:
        logger.exception("Failed to send a password reset email for user %s", user["id"])
        # still the generic response - an unauthenticated caller shouldn't learn SMTP failed

    return GENERIC_FORGOT_PASSWORD_RESPONSE


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest):
    if len(body.new_password) < security.MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {security.MIN_PASSWORD_LENGTH} characters")

    token_hash = security.hash_password_reset_token(body.token)
    reset_token = db.get_valid_password_reset_token(token_hash)
    if reset_token is None:
        raise HTTPException(400, "This reset link is invalid or has expired - request a new one")

    db.set_user_password(reset_token["user_id"], security.hash_password(body.new_password))
    db.mark_password_reset_token_used(token_hash)
    db.delete_all_sessions_for_user(reset_token["user_id"])
    return {"reset": True}
