"""Authenticated git pull / push / fetch inside a project sandbox."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.config import Settings, get_settings
from app.core.deps import get_project_for_member
from app.db.session import get_async_session
from app.models.project import Project
from app.models.user import User
from app.services import git_credentials as git_svc
from app.services.repo_clone import git_remote_op, sanitize_local_path
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

router = APIRouter(tags=["git"])


class GitRemoteRequest(BaseModel):
    path: str = Field(default=".", max_length=200)
    remote: str = Field(default="origin", max_length=64)
    branch: str | None = Field(default=None, max_length=200)


class GitRemoteResult(BaseModel):
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    used_credential: bool


async def _run_op(
    *,
    op: Literal["pull", "push", "fetch"],
    body: GitRemoteRequest,
    project: Project,
    user: User,
    session: AsyncSession,
    settings: Settings,
) -> GitRemoteResult:
    if not project.sandbox_name or project.sandbox_status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Sandbox is not running",
        )
    token, cred = await git_svc.resolve_git_token(
        session,
        user_id=user.id,
        org_id=project.organization_id,
        project_id=project.id,
        provider="github",
        settings=settings,
    )
    client = SandboxAgentClient(settings)
    try:
        result = await git_remote_op(
            client,
            project.sandbox_name,
            op=op,
            path=sanitize_local_path(body.path),
            remote=body.remote.strip() or "origin",
            branch=(body.branch or "").strip() or None,
            token=token,
        )
    except SandboxAgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    if cred is not None and result.get("exit_code") == 0:
        await git_svc.touch_used(session, cred)

    return GitRemoteResult(
        ok=int(result.get("exit_code", 1)) == 0,
        exit_code=int(result.get("exit_code", 1)),
        stdout=str(result.get("stdout") or "")[-4000:],
        stderr=str(result.get("stderr") or "")[-4000:],
        used_credential=bool(token),
    )


@router.post(
    "/projects/{project_id}/git/pull",
    response_model=GitRemoteResult,
)
async def git_pull(
    body: GitRemoteRequest,
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> GitRemoteResult:
    return await _run_op(
        op="pull",
        body=body,
        project=project,
        user=user,
        session=session,
        settings=settings,
    )


@router.post(
    "/projects/{project_id}/git/push",
    response_model=GitRemoteResult,
)
async def git_push(
    body: GitRemoteRequest,
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> GitRemoteResult:
    return await _run_op(
        op="push",
        body=body,
        project=project,
        user=user,
        session=session,
        settings=settings,
    )


@router.post(
    "/projects/{project_id}/git/fetch",
    response_model=GitRemoteResult,
)
async def git_fetch(
    body: GitRemoteRequest,
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> GitRemoteResult:
    return await _run_op(
        op="fetch",
        body=body,
        project=project,
        user=user,
        session=session,
        settings=settings,
    )
