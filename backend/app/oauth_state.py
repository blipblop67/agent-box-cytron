"""
Tiny in-memory CSRF-state store shared by every OAuth connect flow (Gmail,
Drive, Calendar, Sheets). Fine for a single-process hub; would need to move
into the DB if this ever ran multi-process/replicated.
"""
import secrets

_pending: dict[str, str] = {}  # state -> user_id


def create(user_id: str) -> str:
    state = secrets.token_urlsafe(24)
    _pending[state] = user_id
    return state


def pop(state: str) -> str | None:
    return _pending.pop(state, None)
