"""Encrypt/decrypt provider API keys at rest (Fernet).

Uses CREDENTIALS_ENCRYPTION_KEY when set; otherwise derives a Fernet key from
SECRET_KEY (dev/test only — set an explicit key in production).
"""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _fernet_from_secret(raw: str) -> Fernet:
    """Derive a url-safe 32-byte Fernet key from an arbitrary secret string."""
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


@lru_cache
def _get_fernet(key_material: str) -> Fernet:
    return _fernet_from_secret(key_material)


def fernet_for_settings(settings: Settings | None = None) -> Fernet:
    s = settings or get_settings()
    material = (s.credentials_encryption_key or "").strip() or s.secret_key
    if not (s.credentials_encryption_key or "").strip() and s.environment == "production":
        logger.warning(
            "CREDENTIALS_ENCRYPTION_KEY unset in production; falling back to SECRET_KEY",
        )
    return _get_fernet(material)


def encrypt_secret(plaintext: str, settings: Settings | None = None) -> tuple[str, str]:
    """Return (ciphertext_b64, nonce_unused) for storage.

    Fernet embeds its own IV; nonce is stored as empty string for schema stability
    if we later switch to raw AES-GCM.
    """
    token = fernet_for_settings(settings).encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii"), ""


def decrypt_secret(ciphertext: str, nonce: str = "", settings: Settings | None = None) -> str:
    del nonce  # reserved for future AES-GCM
    try:
        raw = fernet_for_settings(settings).decrypt(ciphertext.encode("ascii"))
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt credential") from exc
    return raw.decode("utf-8")


def mask_secret(secret: str, visible: int = 4) -> str:
    """Return a display mask like ••••ab12 (never the full key)."""
    s = secret.strip()
    if not s:
        return "••••"
    if len(s) <= visible:
        return "••••"
    return f"••••{s[-visible:]}"


def clear_crypto_cache() -> None:
    """Test helper — drop cached Fernet instances."""
    _get_fernet.cache_clear()
