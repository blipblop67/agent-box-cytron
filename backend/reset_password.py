#!/usr/bin/env python3
"""
Emergency password reset - for when nobody can log in to reset it from the
web UI (the normal path: Team page -> an admin resets your password). Sets
a password directly in the database, using the exact same hashing the app
itself uses, so the result is completely indistinguishable from a normal
reset - nothing hacky, nothing that leaves the account in a different state
than a regular password change would.

This is a local-shell tool on purpose, not an HTTP endpoint: anyone who can
run this already has full filesystem access to the SQLite database itself
(they could open it directly with any SQLite tool, copy it, delete it) -
there is no additional security to gain by adding friction here, only
friction for the legitimate admin locked out of their own hub. Whoever has
shell access to the machine the hub runs on is the trusted administrator,
by definition, for self-hosted software.

Usage (run on the same machine as the hub, as the same user it runs as -
on the Pi, that's whichever user `deploy/install.sh` was run as):

    cd agent-hub/backend
    python3 reset_password.py
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import db, security  # noqa: E402


def main():
    print("Agent Hub - emergency password reset")
    print("This directly sets a password in the hub's database.\n")

    db.init_db()
    users = db.list_users()

    if not users:
        print("No accounts exist yet - nothing to reset. Just open the hub in a")
        print("browser and register a name + password; the first account becomes admin.")
        return

    print("Accounts on this hub:\n")
    for u in users:
        has_password = "has a password" if u["password_hash"] else "no password set (pre-password-auth account)"
        print(f"  {u['id']:<20} {u['name']:<20} {u['role']:<8} {has_password}")

    print()
    user_id = input("Enter the id of the account to reset (from the list above): ").strip()
    user = db.get_user(user_id)
    if user is None:
        print(f"\nNo account with id '{user_id}'. Nothing changed.")
        sys.exit(1)

    print(f"\nAbout to set a new password for '{user['name']}' (role: {user['role']}).")
    confirm = input("Continue? [y/N] ").strip().lower()
    if confirm != "y":
        print("Cancelled. Nothing changed.")
        return

    while True:
        new_password = getpass.getpass("New password (won't be shown): ")
        if len(new_password) < security.MIN_PASSWORD_LENGTH:
            print(f"Must be at least {security.MIN_PASSWORD_LENGTH} characters - try again.")
            continue
        confirm_password = getpass.getpass("Type it again to confirm: ")
        if new_password != confirm_password:
            print("Those didn't match - try again.")
            continue
        break

    db.set_user_password(user_id, security.hash_password(new_password))
    db.delete_all_sessions_for_user(user_id)  # matches what a normal reset does - forces a fresh login

    print(f"\nDone. '{user['name']}' can log in with the new password now.")
    print("Any existing sessions for this account were signed out, same as a normal reset.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled. Nothing changed.")
