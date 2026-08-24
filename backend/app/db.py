"""
SQLite metadata store. Plain sqlite3 (no ORM) on purpose - this is meant to stay
readable for people learning how the hub works, and a single-writer local DB is
plenty for a small team on one Pi.

Chunk *content* and embeddings live in Chroma (see vector_store.py); this file only
tracks who-owns-what and document ingestion status.
"""
import sqlite3
import time
import uuid
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    password_hash TEXT,
    email TEXT,                            -- optional, only used for password-reset emails
    role TEXT NOT NULL DEFAULT 'member',   -- 'admin' | 'member'
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (user_id, key),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS knowledge_bases (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    owner_id TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'shared',  -- 'shared' (whole team) | 'private' (owner only)
    created_at REAL NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    kb_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_type TEXT,
    size_bytes INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | processing | ready | failed
    error_message TEXT,
    chunk_count INTEGER DEFAULT 0,
    uploaded_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (kb_id) REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS oauth_credentials (
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,          -- 'gmail' | 'drive' (drive lands next)
    encrypted_token BLOB NOT NULL,   -- Fernet-encrypted JSON, see crypto_vault.py
    account_email TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (user_id, provider),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS flows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    owner_id TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'shared',
    graph_json TEXT NOT NULL DEFAULT '{"nodes": [], "edges": []}',
    api_key_hash TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS hub_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    flow_id TEXT NOT NULL,
    trigger_type TEXT NOT NULL,        -- 'interval' | 'daily'
    interval_minutes INTEGER,          -- used when trigger_type = 'interval'
    daily_time TEXT,                   -- 'HH:MM', used when trigger_type = 'daily'
    input_text TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_run_at REAL,
    last_run_status TEXT,              -- 'success' | 'error'
    FOREIGN KEY (flow_id) REFERENCES flows(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS schedule_runs (
    id TEXT PRIMARY KEY,
    schedule_id TEXT NOT NULL,
    flow_id TEXT NOT NULL,
    started_at REAL NOT NULL,
    status TEXT NOT NULL,              -- 'success' | 'error'
    output TEXT,
    error_message TEXT,
    trace_json TEXT,
    FOREIGN KEY (schedule_id) REFERENCES schedules(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    flow_id TEXT NOT NULL,
    user_id TEXT NOT NULL,             -- conversations are personal, not shared - like chat history
    title TEXT NOT NULL DEFAULT 'New conversation',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (flow_id) REFERENCES flows(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,                -- 'user' | 'assistant'
    content TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS telegram_bots (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,                -- e.g. "Support Bot" - what shows up in a Telegram node's picker
    owner_id TEXT NOT NULL,
    visibility TEXT NOT NULL DEFAULT 'shared',  -- 'shared' (whole team) | 'private' (owner only) - same as knowledge_bases
    encrypted_token TEXT NOT NULL,     -- Fernet-encrypted JSON: {bot_token, chat_id}
    bot_username TEXT,
    chat_linked INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS telegram_triggers (
    id TEXT PRIMARY KEY,
    flow_id TEXT NOT NULL,
    bot_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,     -- ongoing memory for this listener, reuses the Chat conversation machinery
    enabled INTEGER NOT NULL DEFAULT 1,
    last_update_id INTEGER,            -- polling position; NULL until the first poll establishes a starting point
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY (flow_id) REFERENCES flows(id) ON DELETE CASCADE,
    FOREIGN KEY (bot_id) REFERENCES telegram_bots(id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS telegram_trigger_runs (
    id TEXT PRIMARY KEY,
    trigger_id TEXT NOT NULL,
    incoming_text TEXT NOT NULL,
    reply_text TEXT,
    status TEXT NOT NULL,              -- 'success' | 'error'
    error_message TEXT,
    started_at REAL NOT NULL,
    FOREIGN KEY (trigger_id) REFERENCES telegram_triggers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_hash TEXT PRIMARY KEY,       -- same fast-hash approach as API keys, not bcrypt - see security.py
    user_id TEXT NOT NULL,
    expires_at REAL NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Schema changes made after this table already shipped."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "password_hash" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    if "email" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")

    flow_columns = {row["name"] for row in conn.execute("PRAGMA table_info(flows)")}
    if "api_key_hash" not in flow_columns:
        conn.execute("ALTER TABLE flows ADD COLUMN api_key_hash TEXT")

    # Telegram used to be one bot connection per user (in oauth_credentials,
    # like Gmail/Drive). It's now a named, ownable resource (like a
    # knowledge base) so different flows can use different bots. Anyone
    # who already had a bot connected the old way gets it carried over
    # automatically as "My bot", once, rather than losing it.
    already_migrated = conn.execute(
        "SELECT 1 FROM hub_settings WHERE key = 'telegram_bots_migrated'"
    ).fetchone()
    if not already_migrated:
        old_rows = conn.execute("SELECT * FROM oauth_credentials WHERE provider = 'telegram'").fetchall()
        for row in old_rows:
            conn.execute(
                "INSERT INTO telegram_bots (id, name, owner_id, visibility, encrypted_token, bot_username, "
                "chat_linked, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id(), "My bot", row["user_id"], "private", row["encrypted_token"],
                 row["account_email"], 1, time.time()),
            )
        conn.execute(
            "INSERT INTO hub_settings (key, value) VALUES ('telegram_bots_migrated', '1') "
            "ON CONFLICT(key) DO NOTHING"
        )


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# ---- users -----------------------------------------------------------------

def create_user(user_id: str, name: str, password_hash: str, role: str | None = None) -> None:
    with get_conn() as conn:
        anyone_exists = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None
        # Bootstrap pattern used by most self-hosted single-box apps: whoever
        # registers first becomes its admin. Everyone after that is a
        # regular member unless an admin promotes them (see set_user_role).
        default_role = role or ("member" if anyone_exists else "admin")
        conn.execute(
            "INSERT INTO users (id, name, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, name, password_hash, default_role, time.time()),
        )


def set_user_password(user_id: str, password_hash: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))


def set_user_email(user_id: str, email: str | None) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        # emails aren't case-sensitive in practice, even though SQLite's
        # default comparison is - COLLATE NOCASE keeps "Alex@x.com" and
        # "alex@x.com" matching the same account
        return conn.execute(
            "SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,)
        ).fetchone()


def set_user_role(user_id: str, role: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def list_users() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()


def get_user(user_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def reassign_user_data(old_user_id: str, new_user_id: str) -> None:
    """Called right before deleting a user: hands off everything they owned
    or created to `new_user_id` (the admin performing the deletion), so
    shared team resources - and anything the schema requires a valid owner
    for - survive the deletion intact rather than hitting a foreign key
    error or vanishing with the account."""
    with get_conn() as conn:
        conn.execute("UPDATE flows SET owner_id = ? WHERE owner_id = ?", (new_user_id, old_user_id))
        conn.execute("UPDATE knowledge_bases SET owner_id = ? WHERE owner_id = ?", (new_user_id, old_user_id))
        conn.execute("UPDATE documents SET uploaded_by = ? WHERE uploaded_by = ?", (new_user_id, old_user_id))
        conn.execute("UPDATE schedules SET created_by = ? WHERE created_by = ?", (new_user_id, old_user_id))
        conn.execute("UPDATE telegram_bots SET owner_id = ? WHERE owner_id = ?", (new_user_id, old_user_id))


def delete_user(user_id: str) -> None:
    with get_conn() as conn:
        # personal connections die with the account - handing someone else's
        # Gmail/Drive/Telegram token to the admin would be nonsensical, unlike
        # flows/knowledge bases which make sense to keep alive for the team
        conn.execute("DELETE FROM oauth_credentials WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        # sessions and user_settings cascade automatically (ON DELETE CASCADE)


# ---- sessions ------------------------------------------------------------------

def create_session(token: str, user_id: str, ttl_seconds: int) -> None:
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, user_id, now, now + ttl_seconds),
        )


def get_session(token: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM sessions WHERE token = ? AND expires_at > ?", (token, time.time()),
        ).fetchone()


def delete_session(token: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def delete_all_sessions_for_user(user_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


# ---- per-user settings (personal Google app / LLM key overrides) ---------------

def get_user_setting(user_id: str, key: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM user_settings WHERE user_id = ? AND key = ?", (user_id, key),
        ).fetchone()
        return row["value"] if row else None


def set_user_setting(user_id: str, key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO user_settings (user_id, key, value) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value",
            (user_id, key, value),
        )


def delete_user_setting(user_id: str, key: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM user_settings WHERE user_id = ? AND key = ?", (user_id, key))


# ---- knowledge bases ---------------------------------------------------------

def create_kb(name: str, description: str, owner_id: str, visibility: str) -> str:
    kb_id = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO knowledge_bases (id, name, description, owner_id, visibility, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (kb_id, name, description, owner_id, visibility, time.time()),
        )
    return kb_id


def get_kb(kb_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM knowledge_bases WHERE id = ?", (kb_id,)).fetchone()


def list_kbs_for_user(user_id: str, is_admin: bool = False) -> list[sqlite3.Row]:
    """Shared KBs (visible to the whole team), this user's own private ones,
    and - for hub admins - every private KB too, for support/moderation."""
    with get_conn() as conn:
        if is_admin:
            return conn.execute("SELECT * FROM knowledge_bases ORDER BY created_at DESC").fetchall()
        return conn.execute(
            "SELECT * FROM knowledge_bases WHERE visibility = 'shared' OR owner_id = ? "
            "ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()


def user_can_access_kb(kb: sqlite3.Row, user_id: str, is_admin: bool = False) -> bool:
    return is_admin or kb["visibility"] == "shared" or kb["owner_id"] == user_id


def delete_kb(kb_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))


# ---- documents ----------------------------------------------------------------

def create_document(kb_id: str, filename: str, content_type: str, size_bytes: int, uploaded_by: str) -> str:
    doc_id = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO documents (id, kb_id, filename, content_type, size_bytes, status, uploaded_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (doc_id, kb_id, filename, content_type, size_bytes, uploaded_by, time.time()),
        )
    return doc_id


def update_document_status(doc_id: str, status: str, chunk_count: int | None = None,
                            error_message: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE documents SET status = ?, chunk_count = COALESCE(?, chunk_count), "
            "error_message = ? WHERE id = ?",
            (status, chunk_count, error_message, doc_id),
        )


def get_document(doc_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()


def list_documents(kb_id: str) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM documents WHERE kb_id = ? ORDER BY created_at DESC", (kb_id,)
        ).fetchall()


def delete_document(doc_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


# ---- oauth credentials (gmail, drive, ...) ------------------------------------

def upsert_oauth_credential(user_id: str, provider: str, encrypted_token: bytes, account_email: str) -> None:
    with get_conn() as conn:
        now = time.time()
        conn.execute(
            "INSERT INTO oauth_credentials (user_id, provider, encrypted_token, account_email, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, provider) DO UPDATE SET "
            "encrypted_token = excluded.encrypted_token, account_email = excluded.account_email, "
            "updated_at = excluded.updated_at",
            (user_id, provider, encrypted_token, account_email, now, now),
        )


def get_oauth_credential(user_id: str, provider: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM oauth_credentials WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        ).fetchone()


def delete_oauth_credential(user_id: str, provider: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM oauth_credentials WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )


# ---- flows ---------------------------------------------------------------------

def create_flow(name: str, description: str, owner_id: str, visibility: str) -> str:
    flow_id = new_id()
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO flows (id, name, description, owner_id, visibility, graph_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, '{\"nodes\": [], \"edges\": []}', ?, ?)",
            (flow_id, name, description, owner_id, visibility, now, now),
        )
    return flow_id


def get_flow(flow_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM flows WHERE id = ?", (flow_id,)).fetchone()


def list_flows_for_user(user_id: str, is_admin: bool = False) -> list[sqlite3.Row]:
    with get_conn() as conn:
        if is_admin:
            return conn.execute("SELECT * FROM flows ORDER BY updated_at DESC").fetchall()
        return conn.execute(
            "SELECT * FROM flows WHERE visibility = 'shared' OR owner_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()


def update_flow(flow_id: str, *, name: str | None = None, description: str | None = None,
                 visibility: str | None = None, graph_json: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE flows SET "
            "name = COALESCE(?, name), description = COALESCE(?, description), "
            "visibility = COALESCE(?, visibility), graph_json = COALESCE(?, graph_json), "
            "updated_at = ? WHERE id = ?",
            (name, description, visibility, graph_json, time.time(), flow_id),
        )


def delete_flow(flow_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM flows WHERE id = ?", (flow_id,))


def user_can_access_flow(flow: sqlite3.Row, user_id: str, is_admin: bool = False) -> bool:
    return is_admin or flow["visibility"] == "shared" or flow["owner_id"] == user_id


def set_flow_api_key_hash(flow_id: str, api_key_hash: str | None) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE flows SET api_key_hash = ? WHERE id = ?", (api_key_hash, flow_id))


def get_flow_by_api_key_hash(api_key_hash: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM flows WHERE api_key_hash = ?", (api_key_hash,)).fetchone()


# ---- hub-wide settings (LLM provider config, etc.) ------------------------------

def get_setting(key: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM hub_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO hub_settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


# ---- schedules -------------------------------------------------------------

def create_schedule(flow_id: str, trigger_type: str, interval_minutes: int | None,
                     daily_time: str | None, input_text: str, created_by: str) -> str:
    schedule_id = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO schedules (id, flow_id, trigger_type, interval_minutes, daily_time, "
            "input_text, enabled, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (schedule_id, flow_id, trigger_type, interval_minutes, daily_time, input_text,
             created_by, time.time()),
        )
    return schedule_id


def get_schedule(schedule_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM schedules WHERE id = ?", (schedule_id,)).fetchone()


def list_schedules_for_flow(flow_id: str) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM schedules WHERE flow_id = ? ORDER BY created_at", (flow_id,)
        ).fetchall()


def list_all_enabled_schedules() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM schedules WHERE enabled = 1").fetchall()


def update_schedule(schedule_id: str, *, enabled: bool | None = None, interval_minutes: int | None = None,
                     daily_time: str | None = None, input_text: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE schedules SET enabled = COALESCE(?, enabled), "
            "interval_minutes = COALESCE(?, interval_minutes), daily_time = COALESCE(?, daily_time), "
            "input_text = COALESCE(?, input_text) WHERE id = ?",
            (int(enabled) if enabled is not None else None, interval_minutes, daily_time, input_text, schedule_id),
        )


def record_schedule_run(schedule_id: str, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE schedules SET last_run_at = ?, last_run_status = ? WHERE id = ?",
            (time.time(), status, schedule_id),
        )


def delete_schedule(schedule_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))


# ---- schedule run history ----------------------------------------------------

def create_schedule_run(schedule_id: str, flow_id: str, status: str, output: str | None,
                         error_message: str | None, trace_json: str | None) -> str:
    run_id = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO schedule_runs (id, schedule_id, flow_id, started_at, status, output, "
            "error_message, trace_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, schedule_id, flow_id, time.time(), status, output, error_message, trace_json),
        )
    return run_id


def list_schedule_runs(schedule_id: str, limit: int = 20) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM schedule_runs WHERE schedule_id = ? ORDER BY started_at DESC LIMIT ?",
            (schedule_id, limit),
        ).fetchall()


# ---- conversations (chat-style memory for a flow) -------------------------------

def create_conversation(flow_id: str, user_id: str, title: str) -> str:
    conversation_id = new_id()
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations (id, flow_id, user_id, title, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (conversation_id, flow_id, user_id, title, now, now),
        )
    return conversation_id


def get_conversation(conversation_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()


def list_conversations(flow_id: str, user_id: str) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM conversations WHERE flow_id = ? AND user_id = ? ORDER BY updated_at DESC",
            (flow_id, user_id),
        ).fetchall()


def touch_conversation(conversation_id: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (time.time(), conversation_id))


def rename_conversation(conversation_id: str, title: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))


def delete_conversation(conversation_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


def add_conversation_message(conversation_id: str, role: str, content: str) -> str:
    message_id = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversation_messages (id, conversation_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (message_id, conversation_id, role, content, time.time()),
        )
    return message_id


def list_conversation_messages(conversation_id: str) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,),
        ).fetchall()


# ---- telegram bots (named, ownable resource - like a knowledge base) -----------
# A bot belongs to whoever created it, with the same shared/private visibility
# as knowledge bases and flows, so different agents can be wired to different
# bots regardless of who happens to run them - unlike Gmail/Drive, a bot is a
# fixed identity in the world (its username), not a personal inbox.

def create_telegram_bot(name: str, owner_id: str, visibility: str, encrypted_token: bytes,
                         bot_username: str) -> str:
    bot_id = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO telegram_bots (id, name, owner_id, visibility, encrypted_token, bot_username, "
            "chat_linked, created_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (bot_id, name, owner_id, visibility, encrypted_token, bot_username, time.time()),
        )
    return bot_id


def get_telegram_bot(bot_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM telegram_bots WHERE id = ?", (bot_id,)).fetchone()


def list_telegram_bots(user_id: str, is_admin: bool = False) -> list[sqlite3.Row]:
    with get_conn() as conn:
        if is_admin:
            return conn.execute("SELECT * FROM telegram_bots ORDER BY created_at DESC").fetchall()
        return conn.execute(
            "SELECT * FROM telegram_bots WHERE visibility = 'shared' OR owner_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()


def user_can_access_telegram_bot(bot: sqlite3.Row, user_id: str, is_admin: bool = False) -> bool:
    return is_admin or bot["visibility"] == "shared" or bot["owner_id"] == user_id


def update_telegram_bot_token(bot_id: str, encrypted_token: bytes, chat_linked: bool) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE telegram_bots SET encrypted_token = ?, chat_linked = ? WHERE id = ?",
            (encrypted_token, int(chat_linked), bot_id),
        )


def rename_telegram_bot(bot_id: str, name: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE telegram_bots SET name = ? WHERE id = ?", (name, bot_id))


def set_telegram_bot_visibility(bot_id: str, visibility: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE telegram_bots SET visibility = ? WHERE id = ?", (visibility, bot_id))


def delete_telegram_bot(bot_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM telegram_bots WHERE id = ?", (bot_id,))


# ---- telegram triggers (listen for messages, run a flow, reply automatically) --

def create_telegram_trigger(flow_id: str, bot_id: str, conversation_id: str, created_by: str) -> str:
    trigger_id = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO telegram_triggers (id, flow_id, bot_id, conversation_id, enabled, "
            "last_update_id, created_by, created_at) VALUES (?, ?, ?, ?, 1, NULL, ?, ?)",
            (trigger_id, flow_id, bot_id, conversation_id, created_by, time.time()),
        )
    return trigger_id


def get_telegram_trigger(trigger_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM telegram_triggers WHERE id = ?", (trigger_id,)).fetchone()


def get_telegram_trigger_for_bot(bot_id: str) -> sqlite3.Row | None:
    """A bot can only be listened to by one trigger at a time - this is how
    that's enforced (see telegram_trigger_routes.py) and how the poller
    finds what to run for a given bot's new messages."""
    with get_conn() as conn:
        return conn.execute("SELECT * FROM telegram_triggers WHERE bot_id = ?", (bot_id,)).fetchone()


def get_telegram_trigger_for_flow(flow_id: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM telegram_triggers WHERE flow_id = ?", (flow_id,)).fetchone()


def list_enabled_telegram_triggers() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM telegram_triggers WHERE enabled = 1").fetchall()


def set_telegram_trigger_enabled(trigger_id: str, enabled: bool) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE telegram_triggers SET enabled = ? WHERE id = ?", (int(enabled), trigger_id))


def set_telegram_trigger_last_update_id(trigger_id: str, last_update_id: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE telegram_triggers SET last_update_id = ? WHERE id = ?", (last_update_id, trigger_id))


def delete_telegram_trigger(trigger_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM telegram_triggers WHERE id = ?", (trigger_id,))


def create_telegram_trigger_run(trigger_id: str, incoming_text: str, reply_text: str | None,
                                 status: str, error_message: str | None) -> str:
    run_id = new_id()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO telegram_trigger_runs (id, trigger_id, incoming_text, reply_text, status, "
            "error_message, started_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, trigger_id, incoming_text, reply_text, status, error_message, time.time()),
        )
    return run_id


def list_telegram_trigger_runs(trigger_id: str, limit: int = 20) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM telegram_trigger_runs WHERE trigger_id = ? ORDER BY started_at DESC LIMIT ?",
            (trigger_id, limit),
        ).fetchall()


# ---- password reset tokens (email-based "forgot password") ---------------------

def create_password_reset_token(token_hash: str, user_id: str, ttl_seconds: int) -> None:
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO password_reset_tokens (token_hash, user_id, expires_at, used, created_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (token_hash, user_id, now + ttl_seconds, now),
        )


def get_valid_password_reset_token(token_hash: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM password_reset_tokens WHERE token_hash = ? AND used = 0 AND expires_at > ?",
            (token_hash, time.time()),
        ).fetchone()


def mark_password_reset_token_used(token_hash: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE password_reset_tokens SET used = 1 WHERE token_hash = ?", (token_hash,))


def invalidate_password_reset_tokens_for_user(user_id: str) -> None:
    """Called whenever a password actually changes some other way (self-service
    change, admin reset, the CLI script) so a stale reset link from before
    that change can't be used to overwrite the new password."""
    with get_conn() as conn:
        conn.execute("UPDATE password_reset_tokens SET used = 1 WHERE user_id = ? AND used = 0", (user_id,))
