"""Create / resolve / revoke preview endpoint GUID bindings."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models.preview import PreviewEndpoint
from app.models.project import Project
from app.services.preview_tickets import mint_ticket


def _base_hostname(base_domain: str) -> str:
    """Hostname part of preview_base_domain (strip leading dots and optional :port)."""
    base = base_domain.lstrip(".").lower()
    return base.split(":")[0]


def _base_with_port(base_domain: str, *, settings: Settings) -> str:
    """Ensure local preview hosts include an explicit port (never silent 80/443).

    - If base already has :port → keep it
    - If preview_public_port is set → append it
    - If host is *.localhost / localhost and scheme is http → default :8000
    - Production bare domains (preview.example.com) stay without port (use 443/80)
    """
    base = (base_domain or "").lstrip(".").strip()
    if not base:
        base = "preview.localhost:8000"

    host_part, sep, port_part = base.partition(":")
    if sep and port_part.isdigit():
        return base

    if settings.preview_public_port and int(settings.preview_public_port) > 0:
        return f"{host_part}:{int(settings.preview_public_port)}"

    host_l = host_part.lower()
    scheme = (settings.preview_public_scheme or "http").rstrip(":/").lower()
    # Local wildcard hosts without a port → API port (preview edge lives on platform-api)
    if scheme == "http" and (host_l == "localhost" or host_l.endswith(".localhost")):
        return f"{host_part}:8000"

    return host_part


def public_preview_url(endpoint_id: UUID, *, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    scheme = settings.preview_public_scheme.rstrip(":/")
    base = _base_with_port(settings.preview_base_domain, settings=settings)
    return f"{scheme}://{endpoint_id}.{base}/"


def parse_endpoint_id_from_host(host: str, *, settings: Settings | None = None) -> UUID | None:
    """Extract endpoint UUID from `{uuid}.{preview_base_domain}` (port stripped)."""
    settings = settings or get_settings()
    if not host:
        return None
    hostname = host.split(":")[0].lower().strip()
    base_host = _base_hostname(settings.preview_base_domain)
    suffix = f".{base_host}"
    if not hostname.endswith(suffix):
        return None
    label = hostname[: -len(suffix)]
    if not label or "." in label:
        return None
    try:
        return UUID(label)
    except ValueError:
        return None


async def get_or_create_endpoint(
    session: AsyncSession,
    *,
    project: Project,
    port: int,
    user_id: UUID,
) -> PreviewEndpoint:
    if not project.sandbox_name:
        raise ValueError("Project has no sandbox")
    if project.sandbox_status != "running":
        raise ValueError(f"Sandbox is not running (status={project.sandbox_status})")
    if port < 1 or port > 65535:
        raise ValueError("Invalid port")

    result = await session.execute(
        select(PreviewEndpoint).where(
            PreviewEndpoint.project_id == project.id,
            PreviewEndpoint.sandbox_name == project.sandbox_name,
            PreviewEndpoint.port == port,
        )
    )
    existing = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if existing:
        existing.last_seen_at = now
        await session.commit()
        await session.refresh(existing)
        return existing

    ep = PreviewEndpoint(
        project_id=project.id,
        sandbox_name=project.sandbox_name,
        port=port,
        created_by_user_id=user_id,
        last_seen_at=now,
    )
    session.add(ep)
    await session.commit()
    await session.refresh(ep)
    return ep


async def resolve_endpoint(session: AsyncSession, endpoint_id: UUID) -> PreviewEndpoint | None:
    result = await session.execute(select(PreviewEndpoint).where(PreviewEndpoint.id == endpoint_id))
    return result.scalar_one_or_none()


async def revoke_endpoints_for_sandbox(
    session: AsyncSession,
    *,
    project_id: UUID,
    sandbox_name: str | None = None,
) -> int:
    stmt = delete(PreviewEndpoint).where(PreviewEndpoint.project_id == project_id)
    if sandbox_name:
        stmt = stmt.where(PreviewEndpoint.sandbox_name == sandbox_name)
    result = await session.execute(stmt)
    await session.commit()
    return int(result.rowcount or 0)


def mint_for_endpoint(
    *,
    endpoint: PreviewEndpoint,
    user_id: UUID,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    token, exp = mint_ticket(
        user_id=user_id,
        endpoint_id=endpoint.id,
        project_id=endpoint.project_id,
        port=endpoint.port,
        settings=settings,
    )
    return {
        "endpoint_id": str(endpoint.id),
        "port": endpoint.port,
        "sandbox_name": endpoint.sandbox_name,
        "url": public_preview_url(endpoint.id, settings=settings),
        "ticket": token,
        "expires_at": exp,
    }
