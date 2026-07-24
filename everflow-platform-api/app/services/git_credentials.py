"""CRUD + resolution for encrypted git PATs."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.git_credential import GitCredential
from app.schemas.git_credential import (
    GitCredentialCreate,
    GitCredentialRead,
    GitCredentialUpdate,
)
from app.services.credential_crypto import decrypt_secret, encrypt_secret


def to_read(row: GitCredential) -> GitCredentialRead:
    return GitCredentialRead(
        id=row.id,
        owner_type=row.owner_type,  # type: ignore[arg-type]
        owner_id=row.owner_id,
        provider=row.provider,
        label=row.label,
        scopes=row.scopes,
        is_default=row.is_default,
        key_hint=f"••••{row.key_last4}" if row.key_last4 else "••••",
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_used_at=row.last_used_at,
    )


async def list_credentials(
    session: AsyncSession,
    *,
    owner_type: str,
    owner_id: UUID,
) -> list[GitCredential]:
    result = await session.execute(
        select(GitCredential)
        .where(
            GitCredential.owner_type == owner_type,
            GitCredential.owner_id == owner_id,
        )
        .order_by(GitCredential.is_default.desc(), GitCredential.created_at.asc())
    )
    return list(result.scalars().all())


async def get_credential(
    session: AsyncSession,
    *,
    cred_id: UUID,
    owner_type: str,
    owner_id: UUID,
) -> GitCredential | None:
    result = await session.execute(
        select(GitCredential).where(
            GitCredential.id == cred_id,
            GitCredential.owner_type == owner_type,
            GitCredential.owner_id == owner_id,
        )
    )
    return result.scalar_one_or_none()


async def _clear_defaults(
    session: AsyncSession,
    *,
    owner_type: str,
    owner_id: UUID,
    provider: str,
) -> None:
    rows = await list_credentials(session, owner_type=owner_type, owner_id=owner_id)
    for row in rows:
        if row.provider == provider and row.is_default:
            row.is_default = False


async def create_credential(
    session: AsyncSession,
    *,
    owner_type: str,
    owner_id: UUID,
    body: GitCredentialCreate,
    settings: Settings | None = None,
) -> GitCredential:
    token = body.token.strip()
    ciphertext, nonce = encrypt_secret(token, settings)
    if body.is_default:
        await _clear_defaults(
            session,
            owner_type=owner_type,
            owner_id=owner_id,
            provider=body.provider,
        )
    row = GitCredential(
        owner_type=owner_type,
        owner_id=owner_id,
        provider=body.provider,
        label=body.label,
        secret_ciphertext=ciphertext,
        secret_nonce=nonce,
        scopes=body.scopes or "repo",
        is_default=body.is_default,
        key_last4=token[-4:] if len(token) >= 4 else token,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_credential(
    session: AsyncSession,
    row: GitCredential,
    body: GitCredentialUpdate,
    settings: Settings | None = None,
) -> GitCredential:
    if body.label is not None:
        row.label = body.label
    if body.scopes is not None:
        row.scopes = body.scopes
    if body.is_default is True:
        await _clear_defaults(
            session,
            owner_type=row.owner_type,
            owner_id=row.owner_id,
            provider=row.provider,
        )
        row.is_default = True
    elif body.is_default is False:
        row.is_default = False
    if body.token is not None:
        token = body.token.strip()
        ciphertext, nonce = encrypt_secret(token, settings)
        row.secret_ciphertext = ciphertext
        row.secret_nonce = nonce
        row.key_last4 = token[-4:] if len(token) >= 4 else token
    await session.commit()
    await session.refresh(row)
    return row


async def delete_credential(session: AsyncSession, row: GitCredential) -> None:
    await session.delete(row)
    await session.commit()


async def decrypt_credential(
    row: GitCredential,
    settings: Settings | None = None,
) -> str:
    return decrypt_secret(row.secret_ciphertext, row.secret_nonce, settings)


async def touch_used(session: AsyncSession, row: GitCredential) -> None:
    row.last_used_at = datetime.now(timezone.utc)
    await session.commit()


async def resolve_git_token(
    session: AsyncSession,
    *,
    user_id: UUID | None,
    org_id: UUID | None,
    project_id: UUID | None,
    provider: str = "github",
    settings: Settings | None = None,
) -> tuple[str | None, GitCredential | None]:
    """Resolve PAT: project → org → user (prefer default)."""
    candidates: list[tuple[str, UUID]] = []
    if project_id is not None:
        candidates.append(("project", project_id))
    if org_id is not None:
        candidates.append(("org", org_id))
    if user_id is not None:
        candidates.append(("user", user_id))

    for owner_type, owner_id in candidates:
        rows = await list_credentials(session, owner_type=owner_type, owner_id=owner_id)
        matching = [r for r in rows if r.provider == provider]
        if not matching:
            continue
        preferred = next((r for r in matching if r.is_default), matching[0])
        token = await decrypt_credential(preferred, settings)
        return token, preferred
    return None, None
