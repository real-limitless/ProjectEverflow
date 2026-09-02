"""Bind each running bot seat to one OpenCode session; kill switch pauses it."""

from __future__ import annotations

import logging
import uuid
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.data.starter_roster import DEFAULT_CONSTITUTION_MD, opencode_agent_payload, starter_agent_pack
from app.models.org import Seat
from app.models.project import Project
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

logger = logging.getLogger(__name__)


def _synthetic_session_id(seat: Seat) -> str:
    return f"ses_{seat.slug}_{uuid.uuid4().hex[:8]}"


async def attach_seat_session(
    session: AsyncSession,
    project: Project,
    seat: Seat,
    *,
    settings: Settings,
    force: bool = False,
) -> Seat:
    if seat.kind != "bot":
        raise ValueError("Only bot seats have a harness session")
    if seat.fired:
        raise ValueError("Seat is fired")
    if seat.paused:
        raise ValueError("Seat is paused — resume before attach")
    if seat.opencode_session_id and not force:
        return seat

    seat.opencode_session_id = _synthetic_session_id(seat)
    seat.status = "idle"
    await _maybe_write_workspace_law(project, seat, settings)
    await sync_seat_to_harness(project, seat, settings)
    await session.commit()
    await session.refresh(seat)
    return seat


async def pause_seat(session: AsyncSession, seat: Seat) -> Seat:
    seat.paused = True
    seat.status = "idle"
    # Keep session id so resume can reattach the same binding; mark paused.
    await session.commit()
    await session.refresh(seat)
    return seat


async def resume_seat(session: AsyncSession, seat: Seat) -> Seat:
    if seat.fired:
        raise ValueError("Cannot resume a fired seat")
    seat.paused = False
    if not seat.opencode_session_id:
        seat.opencode_session_id = _synthetic_session_id(seat)
    await session.commit()
    await session.refresh(seat)
    return seat


async def fire_seat(session: AsyncSession, seat: Seat) -> Seat:
    seat.fired = True
    seat.paused = True
    seat.status = "idle"
    seat.opencode_session_id = None
    await session.commit()
    await session.refresh(seat)
    return seat


async def write_constitution_to_sandbox(
    project: Project,
    settings: Settings,
) -> None:
    body = (project.constitution_md or DEFAULT_CONSTITUTION_MD).strip() + "\n"
    await _write_sandbox_file(project, settings, "constitution.md", body)


async def _maybe_write_workspace_law(
    project: Project,
    seat: Seat,
    settings: Settings,
) -> None:
    if project.sandbox_status != "running" or not project.sandbox_name:
        return
    try:
        await write_constitution_to_sandbox(project, settings)
        if seat.worktree_path and seat.role == "build":
            client = SandboxAgentClient(settings)
            await client.exec(
                project.sandbox_name,
                cmd="mkdir",
                args=["-p", seat.worktree_path],
            )
    except SandboxAgentError as exc:
        logger.info("workspace law write skipped project=%s: %s", project.id, exc)
    except Exception as exc:  # noqa: BLE001
        logger.info("workspace law write failed project=%s: %s", project.id, exc)


async def _write_sandbox_file(
    project: Project,
    settings: Settings,
    path: str,
    body: str,
) -> None:
    if project.sandbox_status != "running" or not project.sandbox_name:
        return
    client = SandboxAgentClient(settings)
    await client.exec(
        project.sandbox_name,
        cmd="sh",
        args=["-c", f"cat > {path} << 'EVERFLOW_EOF'\n{body}EVERFLOW_EOF"],
    )


async def sync_seat_to_harness(project: Project, seat: Seat, settings: Settings) -> None:
    """Best-effort: write this seat's prompt/tools/models into the OpenCode pack."""
    if seat.kind != "bot" or not seat.agent_slug:
        return
    if project.sandbox_status != "running" or not project.sandbox_name:
        return
    spec = {
        "kind": seat.kind,
        "agent_slug": seat.agent_slug,
        "description": seat.description or "",
        "prompt": seat.prompt or "",
        "permission": dict(seat.permission or {}),
        "role": seat.role,
    }
    payload = opencode_agent_payload(spec)
    if not payload:
        return
    if seat.preferred_models:
        payload["model"] = seat.preferred_models[0]
        payload["everflow_models_preferred"] = list(seat.preferred_models)
    try:
        client = SandboxAgentClient(settings)
        await client.put_opencode_harness(
            project.sandbox_name,
            {"agents": [payload]},
        )
    except SandboxAgentError as exc:
        logger.info("harness sync skipped project=%s seat=%s: %s", project.id, seat.slug, exc)
    except Exception as exc:  # noqa: BLE001
        logger.info("harness sync failed project=%s seat=%s: %s", project.id, seat.slug, exc)


def roster_pack_for_harness() -> list[dict]:
    return starter_agent_pack()
