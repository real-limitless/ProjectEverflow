"""Bot bus dispatch, memory, and run compiler."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal, get_principal, get_project_for_principal
from app.db.session import get_async_session
from app.models.bus import MemoryBlock, OrgRun, OrgRunNode
from app.models.project import Project
from app.schemas.bus import (
    BusDispatchBody,
    BusEventRead,
    MemoryRead,
    MemoryUpsert,
    RunCompileBody,
    RunNodePatch,
    RunRead,
)
from app.services.bus import BusError, dispatch, list_events
from app.services.conductor import compile_run
from app.services.org_graph import ensure_starter_company
from app.services.run_read import run_read

router = APIRouter(tags=["bus"])


def _event_read(ev) -> BusEventRead:
    data = BusEventRead.model_validate(ev)
    data.payload = dict(ev.payload or {})
    return data


@router.post(
    "/projects/{project_id}/runs/compile",
    response_model=RunRead,
    status_code=status.HTTP_201_CREATED,
)
async def compile_sentence(
    body: RunCompileBody,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> RunRead:
    principal.require_scope("bus:rw")
    await ensure_starter_company(session, project, owner=principal.user)
    run = await compile_run(
        session,
        project,
        sentence=body.sentence,
        title=body.title,
        channel_id=body.channel_id,
        thread_id=body.thread_id,
        created_by=principal.user,
        start=body.start,
    )
    return await run_read(session, run)


@router.patch("/projects/{project_id}/runs/{run_id}/nodes/{node_id}", response_model=RunRead)
async def patch_run_node(
    run_id: UUID,
    node_id: UUID,
    body: RunNodePatch,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> RunRead:
    principal.require_scope("bus:rw")
    run = await session.get(OrgRun, run_id)
    if run is None or run.project_id != project.id:
        raise HTTPException(status_code=404, detail="Run not found")
    node = await session.get(OrgRunNode, node_id)
    if node is None or node.run_id != run.id:
        raise HTTPException(status_code=404, detail="Node not found")
    if body.status is not None:
        node.status = body.status
    if body.result is not None:
        node.result = body.result
    if body.brief is not None:
        node.brief = body.brief
    await session.commit()
    return await run_read(session, run)


@router.post("/projects/{project_id}/bus", response_model=BusEventRead)
async def bus_dispatch(
    body: BusDispatchBody,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> BusEventRead:
    principal.require_scope("bus:rw")
    try:
        ev = await dispatch(
            session,
            project,
            verb=body.verb,
            from_seat_id=body.from_seat_id,
            to_seat_id=body.to_seat_id,
            to_team_id=body.to_team_id,
            to_channel_id=body.to_channel_id,
            run_id=body.run_id,
            payload=body.payload,
        )
    except BusError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _event_read(ev)


@router.get("/projects/{project_id}/bus/events", response_model=list[BusEventRead])
async def bus_events(
    run_id: UUID | None = Query(default=None),
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[BusEventRead]:
    principal.require_scope("bus:read")
    rows = await list_events(session, project, run_id=run_id)
    return [_event_read(ev) for ev in rows]


@router.put("/projects/{project_id}/memory", response_model=MemoryRead)
async def upsert_memory(
    body: MemoryUpsert,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> MemoryBlock:
    principal.require_scope("bus:rw")
    existing = await session.execute(
        select(MemoryBlock).where(
            MemoryBlock.project_id == project.id,
            MemoryBlock.scope == body.scope,
            MemoryBlock.scope_id == body.scope_id,
            MemoryBlock.name == body.name,
        )
    )
    block = existing.scalar_one_or_none()
    if block is None:
        block = MemoryBlock(
            project_id=project.id,
            scope=body.scope,
            scope_id=body.scope_id,
            name=body.name,
            body=body.body,
        )
        session.add(block)
    else:
        block.body = body.body
    await session.commit()
    await session.refresh(block)
    return block


@router.get("/projects/{project_id}/memory", response_model=list[MemoryRead])
async def list_memory(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[MemoryBlock]:
    principal.require_scope("bus:read")
    result = await session.execute(
        select(MemoryBlock)
        .where(MemoryBlock.project_id == project.id)
        .order_by(MemoryBlock.scope, MemoryBlock.name)
    )
    return list(result.scalars().all())
