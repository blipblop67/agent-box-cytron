"""
Symmetric encryption for OAuth tokens at rest. This whole product runs on a
physical box someone could walk off with, so "store the refresh token as a
plain column" isn't good enough - Fernet gives authenticated encryption with
very little code, which matters more here than picking the fanciest algorithm.

The key lives in its own file, created once, permissioned 0600 (owner
read/write only). Back this file up separately from the database - lose it and
every stored token needs to be reconnected, but that's a far better failure
mode than an unencrypted token sitting in a database file.
"""
import os

from cryptography.fernet import Fernet

from . import config

_KEY_PATH = config.BASE_DIR / "vault.key"


def _load_or_create_key() -> bytes:
    if _KEY_PATH.exists():
        return _KEY_PATH.read_bytes()
    key = Fernet.generate_key()
    _KEY_PATH.write_bytes(key)
    os.chmod(_KEY_PATH, 0o600)
    return key


_fernet = Fernet(_load_or_create_key())


def encrypt(plaintext: str) -> bytes:
    return _fernet.encrypt(plaintext.encode())


def decrypt(ciphertext: bytes) -> str:
    return _fernet.decrypt(ciphertext).decode()
