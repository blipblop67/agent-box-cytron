"""
Password hashing (bcrypt - a real, purpose-built primitive, not homemade)
and session tokens (cryptographically random, opaque, stored server-side).

This is the one place that should ever touch a plaintext password or decide
what makes a valid session.
"""
import hashlib
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


def new_api_key() -> str:
    # prefixed so a leaked key is immediately recognizable as an Agent Hub
    # flow key in a log/commit scan, same idea as ghp_/sk_live_ prefixes
    return f"ahub_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    # Deliberately NOT bcrypt: API keys are high-entropy random tokens, not
    # user-chosen passwords, so there's no offline-guessing risk to slow
    # down - and a published flow needs a fast, indexable lookup by hash on
    # every public API call, which bcrypt is intentionally too slow for.
    return hashlib.sha256(api_key.encode()).hexdigest()


PASSWORD_RESET_TTL_SECONDS = 60 * 60  # 1 hour - short-lived on purpose, it's emailed as a plain link


def new_password_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_password_reset_token(token: str) -> str:
    # Same reasoning as API keys: a high-entropy generated token, not a
    # user-chosen secret, so a fast hash for lookup is correct here too.
    return hashlib.sha256(token.encode()).hexdigest()


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


# ---- password-reset-email throttling ----------------------------------------------
# Separate from login throttling above: this limits how many reset emails
# can be triggered for a given name, not how many wrong passwords were
# tried - protects the SMTP account from being used to spam someone, or
# from burning through a provider's sending quota/rate limit.

RESET_EMAIL_MAX_REQUESTS = 3
RESET_EMAIL_WINDOW_SECONDS = 900  # 15 minutes

_reset_email_requests: dict[str, list[float]] = {}


def can_request_password_reset(name: str) -> bool:
    now = time.time()
    recent = [t for t in _reset_email_requests.get(name, []) if now - t < RESET_EMAIL_WINDOW_SECONDS]
    _reset_email_requests[name] = recent
    return len(recent) < RESET_EMAIL_MAX_REQUESTS


def record_password_reset_request(name: str) -> None:
    _reset_email_requests.setdefault(name, []).append(time.time())
