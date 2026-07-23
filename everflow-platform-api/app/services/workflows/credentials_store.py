"""Encrypt/decrypt workflow credential payloads."""

from __future__ import annotations

import json
from typing import Any

from app.services.credential_crypto import decrypt_secret, encrypt_secret


def encrypt_payload(payload: dict[str, Any]) -> tuple[str, str]:
    return encrypt_secret(json.dumps(payload))


def decrypt_payload(ciphertext: str, nonce: str = "") -> dict[str, Any]:
    raw = decrypt_secret(ciphertext, nonce)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Credential payload must be a JSON object")
    return data
