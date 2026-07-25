"""Mint, verify, and revoke project-scoped sandbox access tokens."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models.sandbox_token import TOKEN_PREFIX, SandboxAccessToken

DEFAULT_SCOPES = [
    "knowledge:rw",
    "agents:rw",
    "tests:rw",
    "http_tools:rw",
    "deploy:rw",
    "jobs:rw",
    "project:read",
]


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_raw_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


async def mint_sandbox_token(
    session: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    scopes: list[str] | None = None,
    label: str | None = None,
    ttl_seconds: int | None = None,
    settings: Settings | None = None,
    revoke_existing: bool = False,
) -> tuple[SandboxAccessToken, str]:
    """Create a token row and return (row, raw_token). Raw is only available once."""
    settings = settings or get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else settings.sandbox_token_ttl_seconds
    now = datetime.now(timezone.utc)

    if revoke_existing:
        await session.execute(
            update(SandboxAccessToken)
            .where(
                SandboxAccessToken.project_id == project_id,
                SandboxAccessToken.user_id == user_id,
                SandboxAccessToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    raw = generate_raw_token()
    row = SandboxAccessToken(
        project_id=project_id,
        user_id=user_id,
        token_hash=_hash_token(raw),
        prefix=raw[:16],
        scopes=list(scopes or DEFAULT_SCOPES),
        label=label or "opencode-mcp",
        expires_at=now + timedelta(seconds=ttl),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row, raw


async def verify_sandbox_token(
    session: AsyncSession,
    raw: str,
) -> SandboxAccessToken | None:
    if not raw or not raw.startswith(TOKEN_PREFIX):
        return None
    digest = _hash_token(raw)
    result = await session.execute(
        select(SandboxAccessToken).where(SandboxAccessToken.token_hash == digest)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    now = datetime.now(timezone.utc)
    if row.revoked_at is not None:
        return None
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp <= now:
        return None
    row.last_used_at = now
    await session.commit()
    await session.refresh(row)
    return row


async def revoke_tokens_for_project(
    session: AsyncSession,
    project_id: UUID,
) -> int:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        update(SandboxAccessToken)
        .where(
            SandboxAccessToken.project_id == project_id,
            SandboxAccessToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await session.commit()
    return int(result.rowcount or 0)


def has_scope(scopes: list[str] | None, required: str) -> bool:
    """Check scope. ``resource:rw`` implies ``resource:read``."""
    if not scopes:
        return False
    if "*" in scopes or required in scopes:
        return True
    if required.endswith(":read"):
        base = required.rsplit(":", 1)[0]
        if f"{base}:rw" in scopes:
            return True
    return False
