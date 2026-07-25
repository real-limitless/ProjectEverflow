"""Marketplace catalog + project install/uninstall APIs."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.config import Settings, get_settings
from app.core.deps import get_project_for_member
from app.db.session import get_async_session
from app.models.http_tool import ProjectHttpTool
from app.models.project import Project
from app.models.user import User
from app.services.marketplace import (
    MarketplaceError,
    build_install_pack,
    build_uninstall_pack,
    catalog_summary,
    find_item,
    get_item_content,
    public_item_fields,
)
from app.services.sandbox import mark_sandbox_missing
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

router = APIRouter(tags=["marketplace"])

MarketplaceKind = Literal["skill", "command", "plugin", "tool", "mcp"]


class MarketplaceInstallBody(BaseModel):
    kind: MarketplaceKind
    item_id: str = Field(min_length=1, max_length=128)


class MarketplaceUninstallBody(BaseModel):
    kind: MarketplaceKind
    item_id: str = Field(min_length=1, max_length=128)


def _http_error(exc: MarketplaceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _require_running_sandbox(project: Project) -> str:
    if not project.sandbox_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project has no sandbox yet",
        )
    if project.sandbox_status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sandbox is not running (status={project.sandbox_status})",
        )
    return project.sandbox_name


def _agent_http_error(exc: SandboxAgentError) -> HTTPException:
    code = exc.status_code or status.HTTP_502_BAD_GATEWAY
    if code == 404:
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if code == 409:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if code == 400:
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if code >= 500 or code is None:
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/marketplace/catalog")
async def get_marketplace_catalog() -> dict[str, Any]:
    """Return the vendored marketplace catalog (ECC + curated)."""
    try:
        return catalog_summary()
    except MarketplaceError as exc:
        raise _http_error(exc) from exc


@router.get("/marketplace/items/{kind}/{item_id}")
async def get_marketplace_item(kind: MarketplaceKind, item_id: str) -> dict[str, Any]:
    """Return a single catalog item (metadata only; no resolved body)."""
    try:
        item = find_item(kind, item_id)
        return public_item_fields(item)
    except MarketplaceError as exc:
        raise _http_error(exc) from exc


@router.get("/marketplace/items/{kind}/{item_id}/content")
async def get_marketplace_item_content(kind: MarketplaceKind, item_id: str) -> dict[str, Any]:
    """Resolve skill/command markdown for App Store detail preview."""
    try:
        return await get_item_content(kind, item_id)
    except MarketplaceError as exc:
        raise _http_error(exc) from exc


@router.get("/projects/{project_id}/marketplace/installed")
async def list_marketplace_installed(
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """List marketplace items installed on the project (harness + HTTP tools)."""
    items: list[dict[str, Any]] = []
    harness: dict[str, Any] | None = None

    if project.sandbox_name and project.sandbox_status == "running":
        client = SandboxAgentClient(settings)
        try:
            harness = await client.get_opencode_harness(project.sandbox_name)
        except SandboxAgentError as exc:
            if exc.status_code == 404:
                await mark_sandbox_missing(session, project)
            else:
                raise _agent_http_error(exc) from exc

    if isinstance(harness, dict):
        manifest = harness.get("manifest") if isinstance(harness.get("manifest"), dict) else {}
        for row in manifest.get("marketplace_items") or []:
            if isinstance(row, dict):
                items.append(row)
        # Fallback: surface managed plugins even without provenance
        for name in harness.get("plugins") or []:
            if not any(i.get("kind") == "plugin" and i.get("id") == name for i in items):
                # Map npm package back to catalog plugin id when possible
                try:
                    find_item("plugin", str(name))
                    items.append({"kind": "plugin", "id": str(name), "source": "opencode.json"})
                except MarketplaceError:
                    items.append(
                        {
                            "kind": "plugin",
                            "id": str(name),
                            "source": "opencode.json",
                            "name": str(name),
                        }
                    )

    # HTTP tools from marketplace presets (by name match)
    result = await session.execute(
        select(ProjectHttpTool).where(ProjectHttpTool.project_id == project.id)
    )
    tools = list(result.scalars().all())
    try:
        catalog_tools = catalog_summary().get("tools") or []
    except MarketplaceError:
        catalog_tools = []
    preset_names = {
        str(t.get("httpTool", {}).get("name") or t.get("id"))
        for t in catalog_tools
        if isinstance(t, dict)
    }
    for tool in tools:
        if tool.name in preset_names or any(
            isinstance(t, dict) and str(t.get("id")) == tool.name for t in catalog_tools
        ):
            if not any(i.get("kind") == "tool" and i.get("id") == tool.name for i in items):
                items.append(
                    {
                        "kind": "tool",
                        "id": tool.name,
                        "source": "http-tools",
                        "name": tool.name,
                        "http_tool_id": str(tool.id),
                    }
                )

    return {
        "project_id": str(project.id),
        "sandbox_status": project.sandbox_status,
        "items": items,
        "plugins": (harness or {}).get("plugins") or [],
        "manifest": (harness or {}).get("manifest") or {},
    }


@router.post("/projects/{project_id}/marketplace/install")
async def install_marketplace_item(
    body: MarketplaceInstallBody,
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Install a catalog item into the project (harness and/or HTTP tools)."""
    try:
        pack = await build_install_pack(body.kind, body.item_id)
    except MarketplaceError as exc:
        raise _http_error(exc) from exc

    http_tool_created: dict[str, Any] | None = None
    if body.kind == "tool":
        http_spec = pack.get("http_tool")
        if not isinstance(http_spec, dict):
            raise HTTPException(status_code=500, detail="Invalid tool pack")
        name = str(http_spec.get("name") or body.item_id)
        existing = await session.execute(
            select(ProjectHttpTool).where(
                ProjectHttpTool.project_id == project.id,
                ProjectHttpTool.name == name,
            )
        )
        tool = existing.scalar_one_or_none()
        if tool is None:
            tool = ProjectHttpTool(
                project_id=project.id,
                name=name,
                method=str(http_spec.get("method") or "GET").upper(),
                url_template=str(http_spec.get("url_template") or ""),
                enabled=bool(http_spec.get("enabled", True)),
                created_by=user.id,
            )
            session.add(tool)
            await session.commit()
            await session.refresh(tool)
        http_tool_created = {
            "id": str(tool.id),
            "name": tool.name,
            "method": tool.method,
            "url_template": tool.url_template,
            "enabled": tool.enabled,
        }
        return {
            "ok": True,
            "kind": body.kind,
            "item_id": body.item_id,
            "http_tool": http_tool_created,
        }

    name = _require_running_sandbox(project)
    # Strip non-harness keys
    harness_body = {k: v for k, v in pack.items() if k != "http_tool"}
    client = SandboxAgentClient(settings)
    try:
        result = await client.put_opencode_harness(name, harness_body)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sandbox missing on agent; recreate the sandbox",
            ) from exc
        raise _agent_http_error(exc) from exc

    # Playwright MCP: force OpenCode restart so the new MCP server spawns.
    opencode: dict | None = None
    if body.kind == "mcp" and body.item_id == "playwright":
        try:
            opencode = await client.opencode_ensure(name, force_restart=True)
        except SandboxAgentError as exc:
            opencode = {"ok": False, "error": str(exc)}

    return {
        "ok": True,
        "kind": body.kind,
        "item_id": body.item_id,
        "harness": result,
        "opencode": opencode,
    }


@router.post("/projects/{project_id}/marketplace/uninstall")
async def uninstall_marketplace_item(
    body: MarketplaceUninstallBody,
    project: Project = Depends(get_project_for_member),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Remove a previously installed marketplace item from the project."""
    try:
        item = find_item(body.kind, body.item_id)
        pack = build_uninstall_pack(body.kind, body.item_id, item)
    except MarketplaceError as exc:
        raise _http_error(exc) from exc

    if body.kind == "tool":
        http_name = str(
            (item.get("httpTool") or {}).get("name") if isinstance(item.get("httpTool"), dict) else body.item_id
        )
        result = await session.execute(
            select(ProjectHttpTool).where(
                ProjectHttpTool.project_id == project.id,
                ProjectHttpTool.name == http_name,
            )
        )
        tool = result.scalar_one_or_none()
        if tool is not None:
            await session.delete(tool)
            await session.commit()
        return {"ok": True, "kind": body.kind, "item_id": body.item_id, "removed": tool is not None}

    name = _require_running_sandbox(project)
    harness_body = {k: v for k, v in pack.items() if k != "remove_http_tool_name"}
    client = SandboxAgentClient(settings)
    try:
        result = await client.put_opencode_harness(name, harness_body)
    except SandboxAgentError as exc:
        if exc.status_code == 404:
            await mark_sandbox_missing(session, project)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Sandbox missing on agent; recreate the sandbox",
            ) from exc
        raise _agent_http_error(exc) from exc

    return {
        "ok": True,
        "kind": body.kind,
        "item_id": body.item_id,
        "harness": result,
    }
