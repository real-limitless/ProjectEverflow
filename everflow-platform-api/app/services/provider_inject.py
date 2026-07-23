"""Resolve vault credentials and inject them into a project sandbox."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.project import Project
from app.services.providers import (
    PROVIDER_ENV_NAMES,
    decrypt_row,
    list_credentials,
)
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

logger = logging.getLogger(__name__)

ENV_TO_PROVIDER: dict[str, str] = {v: k for k, v in PROVIDER_ENV_NAMES.items()}


async def resolve_effective_secrets(
    session: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    settings: Settings,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return (env_map, providers_map) without logging values.

    Project credentials override user credentials for the same provider.
    """
    env: dict[str, str] = {}
    providers: dict[str, str] = {}

    for owner_type, owner_id in (("user", user_id), ("project", project_id)):
        rows = await list_credentials(session, owner_type=owner_type, owner_id=owner_id)
        for row in rows:
            try:
                secret = decrypt_row(row, settings)
            except ValueError:
                logger.warning(
                    "skip undecryptable credential id=%s provider=%s",
                    row.id,
                    row.provider,
                )
                continue
            env_name = PROVIDER_ENV_NAMES.get(row.provider)
            if env_name:
                env[env_name] = secret
            providers[row.provider] = secret

    return env, providers


async def inject_project_provider_secrets(
    session: AsyncSession,
    project: Project,
    *,
    user_id: UUID,
    settings: Settings,
    client: SandboxAgentClient | None = None,
    apply_opencode_auth: bool = True,
) -> dict[str, Any]:
    """Inject vault secrets into a running sandbox. Best-effort OpenCode auth.

    Returns a public summary (key names only, never secret values).
    """
    if not project.sandbox_name:
        return {
            "injected": False,
            "reason": "no_sandbox",
            "env_keys": [],
            "opencode_providers": [],
        }
    if project.sandbox_status != "running":
        return {
            "injected": False,
            "reason": f"sandbox_{project.sandbox_status}",
            "env_keys": [],
            "opencode_providers": [],
        }

    env, providers = await resolve_effective_secrets(
        session,
        project_id=project.id,
        user_id=user_id,
        settings=settings,
    )
    if not env and not providers:
        return {
            "injected": False,
            "reason": "no_credentials",
            "env_keys": [],
            "opencode_providers": [],
        }

    client = client or SandboxAgentClient(settings)
    try:
        result = await client.inject_provider_secrets(
            project.sandbox_name,
            env=env,
            providers=providers,
        )
    except SandboxAgentError as exc:
        logger.warning(
            "provider secret inject failed project=%s: %s",
            project.id,
            exc,
        )
        return {
            "injected": False,
            "reason": "agent_error",
            "env_keys": [],
            "opencode_providers": [],
            "error": str(exc)[:500],
        }

    opencode_ok: list[str] = []
    if apply_opencode_auth and providers:
        for pid, key in providers.items():
            try:
                await client.opencode_set_auth(project.sandbox_name, pid, key)
                opencode_ok.append(pid)
            except SandboxAgentError as exc:
                # OpenCode may not be up yet — env file is still written
                logger.debug(
                    "opencode auth set skipped project=%s provider=%s: %s",
                    project.id,
                    pid,
                    exc,
                )

    logger.info(
        "provider secrets injected project=%s env_keys=%s opencode=%s",
        project.id,
        sorted(env.keys()),
        opencode_ok,
    )
    return {
        "injected": True,
        "reason": "ok",
        "env_keys": list(result.get("env_keys") or sorted(env.keys())),
        "opencode_providers": opencode_ok,
        "path": result.get("path"),
    }
