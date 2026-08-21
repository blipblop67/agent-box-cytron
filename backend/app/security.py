"""
Password hashing (bcrypt - a real, purpose-built primitive, not homemade)
and session tokens (cryptographically random, opaque, stored server-side).

This is the one place that should ever touch a plaintext password or decide
what makes a valid session.
"""
import secrets
import time

import bcrypt

MIN_PASSWORD_LENGTH = 8
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        # malformed/legacy hash - never crash the login attempt over it
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


# ---- login throttling ------------------------------------------------------------
# In-memory, per display name (not per-IP - on a LAN, IPs are often shared/NATed,
# and the name is the more meaningful identity boundary for this threat model).
# Resets on restart; that's an acceptable trade for a single-process hub, not a
# service worth adding Redis for.

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 300

_failed_attempts: dict[str, list[float]] = {}


def _recent_attempts(name: str) -> list[float]:
    now = time.time()
    attempts = [t for t in _failed_attempts.get(name, []) if now - t < WINDOW_SECONDS]
    _failed_attempts[name] = attempts
    return attempts


def is_locked_out(name: str) -> bool:
    return len(_recent_attempts(name)) >= MAX_ATTEMPTS


def record_failed_attempt(name: str) -> None:
    _recent_attempts(name).append(time.time())


def clear_attempts(name: str) -> None:
    _failed_attempts.pop(name, None)
