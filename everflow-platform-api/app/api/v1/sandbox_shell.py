"""Interactive sandbox shell WebSocket — JWT auth, proxies to sandbox-agent."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from starlette.websockets import WebSocketState

from app.auth.users import UserManager, get_jwt_strategy
from app.config import get_settings
from app.db.session import get_session_factory
from app.models.organization import OrganizationMember
from app.models.project import Project
from app.models.user import OAuthAccount, User
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sandbox"])


async def _user_from_token(token: str) -> User | None:
    factory = get_session_factory()
    async with factory() as session:
        user_db = SQLAlchemyUserDatabase(session, User, OAuthAccount)
        manager = UserManager(user_db)
        strategy = get_jwt_strategy()
        user = await strategy.read_token(token, manager)
        if user is None or not user.is_active:
            return None
        # Detach for use after session closes
        session.expunge(user)
        return user


async def _project_for_member(project_id: UUID, user_id: UUID) -> Project | None:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Project).where(Project.id == project_id))
        project = result.scalar_one_or_none()
        if project is None:
            return None
        mem = await session.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == project.organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        if mem.scalar_one_or_none() is None:
            return None
        session.expunge(project)
        return project


def _agent_ws_url(sandbox_name: str, cmd: str | None, cwd: str) -> str:
    settings = get_settings()
    base = settings.sandbox_agent_url.rstrip("/")
    # http → ws
    if base.startswith("https://"):
        ws_base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        ws_base = "ws://" + base[len("http://") :]
    else:
        ws_base = base
    from urllib.parse import quote, urlencode

    q: dict[str, str] = {
        "token": settings.sandbox_agent_token,
        "cwd": cwd or "/workspace",
    }
    if cmd:
        q["cmd"] = cmd
    return f"{ws_base}/v1/sandboxes/{quote(sandbox_name, safe='')}/shell?{urlencode(q)}"


@router.websocket("/projects/{project_id}/sandbox/shell")
async def project_sandbox_shell(
    websocket: WebSocket,
    project_id: UUID,
    token: str = Query(default=""),
    cmd: str | None = Query(default=None),
    cwd: str = Query(default="/workspace"),
) -> None:
    """
    Browser-facing interactive PTY.

    Connect: ws://api/api/v1/projects/{id}/sandbox/shell?token=<JWT>
    Proxies JSON frames to sandbox-agent shell WebSocket.
    """
    await websocket.accept()
    settings = get_settings()
    if not settings.sandbox_enabled:
        await websocket.send_json({"type": "error", "message": "Sandbox disabled"})
        await websocket.close(code=4403)
        return
    if not token:
        await websocket.send_json({"type": "error", "message": "Missing token"})
        await websocket.close(code=4401)
        return

    user = await _user_from_token(token)
    if user is None:
        await websocket.send_json({"type": "error", "message": "Invalid or expired token"})
        await websocket.close(code=4401)
        return

    project = await _project_for_member(project_id, user.id)
    if project is None:
        await websocket.send_json({"type": "error", "message": "Project not found"})
        await websocket.close(code=4404)
        return
    if not project.sandbox_name:
        await websocket.send_json({"type": "error", "message": "Project has no sandbox"})
        await websocket.close(code=4409)
        return
    if project.sandbox_status != "running":
        await websocket.send_json(
            {
                "type": "error",
                "message": f"Sandbox not running (status={project.sandbox_status}). Recreate if missing.",
            }
        )
        # still allow connect attempt if status is stale — agent will error

    url = _agent_ws_url(project.sandbox_name, cmd, cwd)
    try:
        import websockets
        from websockets.exceptions import ConnectionClosed
    except ImportError:
        await websocket.send_json(
            {"type": "error", "message": "websockets package not installed on API"}
        )
        await websocket.close()
        return

    agent_ws: Any = None
    try:
        agent_ws = await websockets.connect(url, open_timeout=30, max_size=8 * 1024 * 1024)
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent shell connect failed")
        await websocket.send_json({"type": "error", "message": f"Agent connect failed: {exc}"})
        await websocket.close()
        return

    stop = asyncio.Event()

    async def client_to_agent() -> None:
        try:
            while not stop.is_set():
                try:
                    msg = await websocket.receive_text()
                except WebSocketDisconnect:
                    break
                await agent_ws.send(msg)
        except Exception:
            pass
        finally:
            stop.set()

    async def agent_to_client() -> None:
        try:
            async for msg in agent_ws:
                if websocket.client_state != WebSocketState.CONNECTED:
                    break
                if isinstance(msg, bytes):
                    await websocket.send_bytes(msg)
                else:
                    await websocket.send_text(msg)
        except ConnectionClosed:
            pass
        except Exception:
            pass
        finally:
            stop.set()

    t1 = asyncio.create_task(client_to_agent())
    t2 = asyncio.create_task(agent_to_client())
    try:
        await stop.wait()
    finally:
        t1.cancel()
        t2.cancel()
        try:
            await agent_ws.close()
        except Exception:
            pass
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()
        except Exception:
            pass
