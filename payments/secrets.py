"""Application-level encryption for admin-entered PAYMENT credentials (Stripe / PayPal).

Mirrors ``printify_integration.secrets`` but with a SEPARATE Fernet key
(``PAYMENT_CONFIG_KEY``) so payment secrets have their own blast radius. Plaintext secrets are
NEVER stored, logged, rendered or returned to the browser — only decrypted server-side at call
time (test connection / checkout). If the key is missing, saving a secret is refused with a
clear error (fail-closed). A one-way fingerprint + last-4 let the admin see a secret is present
(and detect change) without ever revealing it.

Generate a key once and put it in the server env (never in the repo):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # -> PAYMENT_CONFIG_KEY=...
"""
import hashlib

from django.conf import settings

KEY_SETTING = "PAYMENT_CONFIG_KEY"


class SecretKeyMissing(Exception):
    """Raised when PAYMENT_CONFIG_KEY is not configured but a secret op is attempted."""


def has_key() -> bool:
    return bool(getattr(settings, KEY_SETTING, ""))


def _fernet():
    key = getattr(settings, KEY_SETTING, "") or ""
    if not key:
        raise SecretKeyMissing(
            "PAYMENT_CONFIG_KEY is not set — cannot encrypt/decrypt payment secrets. "
            "Set it in the server environment (a Fernet key)."
        )
    from cryptography.fernet import Fernet
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    """Return Fernet ciphertext for a secret. Raises SecretKeyMissing if no key."""
    return _fernet().encrypt((plaintext or "").strip().encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Return the plaintext secret (server-side use only — never render). Empty on failure."""
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        return ""


def fingerprint(plaintext: str) -> str:
    """Short, non-reversible id proving a secret is present / detecting change. Never the secret."""
    p = (plaintext or "").strip()
    return hashlib.sha256(p.encode()).hexdigest()[:12] if p else ""


def last_four(plaintext: str) -> str:
    p = (plaintext or "").strip()
    return p[-4:] if len(p) >= 4 else ""
