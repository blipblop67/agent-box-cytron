"""
Proves the upgrade path: a hub with an old-style single Telegram connection
(from before bots were named, ownable resources) gets that connection
carried forward automatically as "My bot" the first time the new code runs,
rather than losing it. Simulates a pre-upgrade database directly rather than
going through the API, since the old connect/link endpoints this data shape
came from no longer exist.
Run with: python3 tests/test_telegram_migration.py
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ["AGENT_HUB_DATA_DIR"] = tempfile.mkdtemp(prefix="agent-hub-telegram-migration-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, crypto_vault, db, telegram_tokens  # noqa: E402


def main():
    # Simulate a pre-upgrade database: just enough of the old schema for a
    # user with a single-style Telegram connection in oauth_credentials -
    # this is exactly the state a real hub would be in the moment before its
    # first startup on the new code, which is what triggers the migration.
    conn = sqlite3.connect(config.SQLITE_PATH)
    conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT, password_hash TEXT, role TEXT, created_at REAL)")
    conn.execute(
        "CREATE TABLE oauth_credentials (user_id TEXT, provider TEXT, encrypted_token BLOB, "
        "account_email TEXT, connected_at REAL)"
    )
    conn.execute("INSERT INTO users VALUES ('alex', 'Alex', 'fakehash', 'admin', 0)")
    payload = json.dumps({"bot_token": "OLD:TOKEN", "chat_id": 12345})
    conn.execute(
        "INSERT INTO oauth_credentials VALUES (?, ?, ?, ?, ?)",
        ("alex", "telegram", crypto_vault.encrypt(payload), "@old_style_bot", 0),
    )
    conn.commit()
    conn.close()
    print("[ok] simulated a pre-upgrade database with a legacy Telegram connection")

    # This is the moment of upgrading: the new code's init_db() runs for the first time.
    db.init_db()

    bots = db.list_telegram_bots("alex", is_admin=True)
    assert len(bots) == 1, bots
    assert bots[0]["name"] == "My bot"
    assert bots[0]["bot_username"] == "@old_style_bot"
    assert bool(bots[0]["chat_linked"]) is True
    assert bots[0]["visibility"] == "private"
    print("[ok] the legacy connection was carried forward as a private bot named 'My bot'")

    creds = telegram_tokens.get_credentials(bots[0]["id"])
    assert creds["bot_token"] == "OLD:TOKEN"
    assert creds["chat_id"] == 12345
    print("[ok] the migrated bot's token and linked chat id are intact")

    # Subsequent restarts (init_db runs on every startup) must not duplicate it.
    db.init_db()
    db.init_db()
    bots_again = db.list_telegram_bots("alex", is_admin=True)
    assert len(bots_again) == 1, bots_again
    print("[ok] migration runs exactly once - repeated restarts don't duplicate the bot")

    print("\nAll Telegram migration smoke tests passed.")


if __name__ == "__main__":
    main()
