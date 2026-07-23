"""CRUD + resolution helpers for AI provider credentials."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.provider_credential import ProviderCredential
from app.schemas.provider import (
    ProviderCredentialCreate,
    ProviderCredentialRead,
    ProviderCredentialUpdate,
)
from app.services.credential_crypto import decrypt_secret, encrypt_secret, mask_secret

PROVIDER_ENV_NAMES: dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "custom": "CUSTOM_API_KEY",
}

PROVIDER_CATALOG = [
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "description": "One key for many chat and embedding models",
        "scopes": ["chat", "embed", "ocr"],
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "description": "Chat, embeddings, and vision models",
        "scopes": ["chat", "embed", "ocr"],
    },
    {
        "id": "anthropic",
        "name": "Anthropic",
        "description": "Claude chat and vision models",
        "scopes": ["chat", "ocr"],
    },
    {
        "id": "xai",
        "name": "xAI",
        "description": "Grok models",
        "scopes": ["chat"],
    },
]


def scopes_to_str(scopes: list[str] | None) -> str:
    if not scopes:
        return "*"
    cleaned = sorted({s.strip() for s in scopes if s and s.strip()})
    return ",".join(cleaned) if cleaned else "*"


def scopes_from_str(raw: str | None) -> list[str]:
    if not raw or raw.strip() == "*":
        return ["*"]
    return [p for p in (x.strip() for x in raw.split(",")) if p]


def to_read(row: ProviderCredential) -> ProviderCredentialRead:
    return ProviderCredentialRead(
        id=row.id,
        owner_type=row.owner_type,  # type: ignore[arg-type]
        owner_id=row.owner_id,
        provider=row.provider,
        label=row.label,
        scopes=scopes_from_str(row.scopes),
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
) -> list[ProviderCredential]:
    result = await session.execute(
        select(ProviderCredential)
        .where(
            ProviderCredential.owner_type == owner_type,
            ProviderCredential.owner_id == owner_id,
        )
        .order_by(ProviderCredential.provider.asc(), ProviderCredential.created_at.asc())
    )
    return list(result.scalars().all())


async def get_credential(
    session: AsyncSession,
    *,
    cred_id: UUID,
    owner_type: str,
    owner_id: UUID,
) -> ProviderCredential | None:
    result = await session.execute(
        select(ProviderCredential).where(
            ProviderCredential.id == cred_id,
            ProviderCredential.owner_type == owner_type,
            ProviderCredential.owner_id == owner_id,
        )
    )
    return result.scalar_one_or_none()


async def _clear_default_for_provider(
    session: AsyncSession,
    *,
    owner_type: str,
    owner_id: UUID,
    provider: str,
    except_id: UUID | None = None,
) -> None:
    rows = await list_credentials(session, owner_type=owner_type, owner_id=owner_id)
    for row in rows:
        if row.provider != provider:
            continue
        if except_id is not None and row.id == except_id:
            continue
        if row.is_default:
            row.is_default = False


async def create_credential(
    session: AsyncSession,
    *,
    owner_type: str,
    owner_id: UUID,
    body: ProviderCredentialCreate,
    settings: Settings,
) -> ProviderCredential:
    # Upsert by owner+provider: one active key per provider per owner for MVP uniqueness
    existing = await session.execute(
        select(ProviderCredential).where(
            ProviderCredential.owner_type == owner_type,
            ProviderCredential.owner_id == owner_id,
            ProviderCredential.provider == body.provider,
        )
    )
    row = existing.scalar_one_or_none()
    ciphertext, nonce = encrypt_secret(body.api_key, settings)
    last4 = body.api_key[-4:] if len(body.api_key) >= 4 else body.api_key

    if row is None:
        row = ProviderCredential(
            owner_type=owner_type,
            owner_id=owner_id,
            provider=body.provider,
            label=body.label,
            secret_ciphertext=ciphertext,
            secret_nonce=nonce,
            scopes=scopes_to_str(body.scopes),  # type: ignore[arg-type]
            is_default=body.is_default,
            key_last4=last4,
        )
        session.add(row)
    else:
        row.label = body.label if body.label is not None else row.label
        row.secret_ciphertext = ciphertext
        row.secret_nonce = nonce
        row.scopes = scopes_to_str(body.scopes)  # type: ignore[arg-type]
        row.is_default = body.is_default
        row.key_last4 = last4
        row.updated_at = datetime.now(timezone.utc)

    await session.flush()
    if body.is_default:
        await _clear_default_for_provider(
            session,
            owner_type=owner_type,
            owner_id=owner_id,
            provider=body.provider,
            except_id=row.id,
        )

    await session.commit()
    await session.refresh(row)
    return row


async def update_credential(
    session: AsyncSession,
    row: ProviderCredential,
    body: ProviderCredentialUpdate,
    settings: Settings,
) -> ProviderCredential:
    if body.label is not None:
        row.label = body.label
    if body.scopes is not None:
        row.scopes = scopes_to_str(body.scopes)  # type: ignore[arg-type]
    if body.api_key is not None:
        ciphertext, nonce = encrypt_secret(body.api_key, settings)
        row.secret_ciphertext = ciphertext
        row.secret_nonce = nonce
        row.key_last4 = body.api_key[-4:] if len(body.api_key) >= 4 else body.api_key
    if body.is_default is not None:
        row.is_default = body.is_default
        if body.is_default:
            await session.flush()
            await _clear_default_for_provider(
                session,
                owner_type=row.owner_type,
                owner_id=row.owner_id,
                provider=row.provider,
                except_id=row.id,
            )
    row.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(row)
    return row


async def delete_credential(session: AsyncSession, row: ProviderCredential) -> None:
    await session.delete(row)
    await session.commit()


def decrypt_row(row: ProviderCredential, settings: Settings) -> str:
    return decrypt_secret(row.secret_ciphertext, row.secret_nonce, settings)


async def resolve_provider_secrets(
    session: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    settings: Settings,
) -> dict[str, str]:
    """Resolve effective env map for a project: project keys override user keys.

    Returns {ENV_NAME: secret} suitable for sandbox injection. Never log this dict.
    """
    env: dict[str, str] = {}

    user_rows = await list_credentials(session, owner_type="user", owner_id=user_id)
    for row in user_rows:
        env_name = PROVIDER_ENV_NAMES.get(row.provider)
        if not env_name:
            continue
        try:
            env[env_name] = decrypt_row(row, settings)
        except ValueError:
            continue

    project_rows = await list_credentials(session, owner_type="project", owner_id=project_id)
    for row in project_rows:
        env_name = PROVIDER_ENV_NAMES.get(row.provider)
        if not env_name:
            continue
        try:
            env[env_name] = decrypt_row(row, settings)
        except ValueError:
            continue

    return env


def hint_only(secret: str) -> str:
    return mask_secret(secret)
