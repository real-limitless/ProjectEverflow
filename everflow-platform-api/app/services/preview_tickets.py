"""Signed short-lived tickets for iframe-safe preview auth."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.config import Settings, get_settings


class PreviewTicketError(Exception):
    def __init__(self, message: str, *, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PreviewTicketClaims:
    user_id: UUID
    endpoint_id: UUID
    project_id: UUID
    port: int
    exp: int
    jti: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sub": str(self.user_id),
            "eid": str(self.endpoint_id),
            "pid": str(self.project_id),
            "port": self.port,
            "exp": self.exp,
            "jti": self.jti,
        }


def _b64e(raw: bytes) -> str:
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(raw: str) -> bytes:
    pad = "=" * (-len(raw) % 4)
    return urlsafe_b64decode(raw + pad)


def _sign(payload_b64: str, secret: str) -> str:
    dig = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64e(dig)


def mint_ticket(
    *,
    user_id: UUID,
    endpoint_id: UUID,
    project_id: UUID,
    port: int,
    settings: Settings | None = None,
    jti: str | None = None,
) -> tuple[str, int]:
    """Return (token, expires_at_unix)."""
    settings = settings or get_settings()
    now = int(time.time())
    exp = now + int(settings.preview_ticket_ttl_seconds)
    import secrets

    claims = PreviewTicketClaims(
        user_id=user_id,
        endpoint_id=endpoint_id,
        project_id=project_id,
        port=port,
        exp=exp,
        jti=jti or secrets.token_urlsafe(12),
    )
    payload_b64 = _b64e(json.dumps(claims.to_dict(), separators=(",", ":")).encode("utf-8"))
    sig = _sign(payload_b64, settings.secret_key)
    return f"{payload_b64}.{sig}", exp


def verify_ticket(token: str, *, settings: Settings | None = None) -> PreviewTicketClaims:
    settings = settings or get_settings()
    if not token or "." not in token:
        raise PreviewTicketError("Invalid ticket")
    payload_b64, sig = token.rsplit(".", 1)
    expected = _sign(payload_b64, settings.secret_key)
    if not hmac.compare_digest(sig, expected):
        raise PreviewTicketError("Invalid ticket signature")
    try:
        data = json.loads(_b64d(payload_b64).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise PreviewTicketError("Invalid ticket payload") from exc

    exp = int(data.get("exp") or 0)
    if exp < int(time.time()):
        raise PreviewTicketError("Ticket expired", status_code=401)

    try:
        return PreviewTicketClaims(
            user_id=UUID(str(data["sub"])),
            endpoint_id=UUID(str(data["eid"])),
            project_id=UUID(str(data["pid"])),
            port=int(data["port"]),
            exp=exp,
            jti=str(data.get("jti") or ""),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise PreviewTicketError("Invalid ticket claims") from exc
