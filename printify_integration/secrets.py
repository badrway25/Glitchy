"""Application-level encryption for admin-entered Printify credentials.

The Printify API token entered in the admin is encrypted at rest with Fernet using a key
from the environment (``PRINTIFY_CONFIG_KEY``). The plaintext token is NEVER stored, logged,
rendered, or returned to the browser — it is only decrypted server-side at call time (sync /
test connection). If the key is missing, saving a token is refused with a clear error
(fail-closed). A one-way fingerprint lets the admin see that a token is present (and whether
it changed) without ever revealing it.

Generate a key once and put it in the server env (never in the repo):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # -> PRINTIFY_CONFIG_KEY=...
"""
import hashlib

from django.conf import settings


class SecretKeyMissing(Exception):
    """Raised when PRINTIFY_CONFIG_KEY is not configured but a token op is attempted."""


def has_key() -> bool:
    return bool(getattr(settings, "PRINTIFY_CONFIG_KEY", ""))


def _fernet():
    key = getattr(settings, "PRINTIFY_CONFIG_KEY", "") or ""
    if not key:
        raise SecretKeyMissing(
            "PRINTIFY_CONFIG_KEY is not set — cannot encrypt/decrypt the Printify token. "
            "Set it in the server environment (a Fernet key)."
        )
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(plaintext: str) -> str:
    """Return Fernet ciphertext for a token. Raises SecretKeyMissing if no key."""
    return _fernet().encrypt((plaintext or "").strip().encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Return the plaintext token (server-side use only — never render). Empty on failure."""
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        return ""


def fingerprint(plaintext: str) -> str:
    """A short, non-reversible id to show 'a token is present' / detect change. Never the token."""
    p = (plaintext or "").strip()
    return hashlib.sha256(p.encode()).hexdigest()[:12] if p else ""
