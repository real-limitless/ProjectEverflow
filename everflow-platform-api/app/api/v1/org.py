"""Teams, seats, chart, constitution, add/pause/remove/attach."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.principal import Principal, get_principal, get_project_for_principal
from app.data.starter_roster import DEFAULT_CONSTITUTION_MD, starter_agent_pack
from app.db.session import get_async_session
from app.models.org import Seat, Team
from app.models.project import Project
from app.schemas.org import (
    ChartEdge,
    ChartRead,
    ConstitutionRead,
    ConstitutionUpdate,
    SeatCreate,
    SeatRead,
    SeatReparent,
    SeatUpdate,
    TeamCreate,
    TeamRead,
    TeamUpdate,
)
from app.services.org_graph import (
    OrgGraphError,
    ensure_starter_company,
    export_multi_team_yaml,
    hire_defaults,
    list_chart,
    reparent_seat,
    would_cycle,
)
from app.services.session_bind import (
    attach_seat_session,
    fire_seat,
    pause_seat,
    resume_seat,
    write_constitution_to_sandbox,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["org"])


def _seat_read(seat: Seat) -> SeatRead:
    data = SeatRead.model_validate(seat)
    data.permission = dict(seat.permission or {})
    data.tools = [str(t) for t in (seat.tools or [])]
    data.prompt = seat.prompt or ""
    data.skills = [str(t) for t in (seat.skills or [])]
    data.preferred_models = [str(t) for t in (seat.preferred_models or [])]
    return data


def _filter_seats(seats: list[Seat], include_system: bool) -> list[Seat]:
    if include_system:
        return seats
    return [s for s in seats if not s.is_conductor]


async def _get_seat(session: AsyncSession, project_id: UUID, seat_id: UUID) -> Seat:
    result = await session.execute(
        select(Seat).where(Seat.id == seat_id, Seat.project_id == project_id)
    )
    seat = result.scalar_one_or_none()
    if seat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seat not found")
    return seat


@router.post("/projects/{project_id}/org/ensure", response_model=ChartRead)
async def ensure_org(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> ChartRead:
    principal.require_scope("org:rw")
    teams, seats, _channels = await ensure_starter_company(
        session, project, owner=principal.user
    )
    try:
        await write_constitution_to_sandbox(project, get_settings())
    except Exception:  # noqa: BLE001
        pass
    return ChartRead(
        teams=[TeamRead.model_validate(t) for t in teams],
        seats=[_seat_read(s) for s in seats],
        edges=[
            ChartEdge(from_id=s.reports_to_id, to_id=s.id)
            for s in seats
            if s.reports_to_id
        ],
        constitution_md=project.constitution_md or DEFAULT_CONSTITUTION_MD,
    )


@router.get("/projects/{project_id}/chart", response_model=ChartRead)
async def get_chart(
    include_system: bool = Query(default=False),
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> ChartRead:
    principal.require_scope("org:read")
    teams, seats = await list_chart(session, project, include_system=include_system)
    if not seats:
        teams, seats, _ = await ensure_starter_company(session, project, owner=principal.user)
        seats = _filter_seats(seats, include_system)
    visible = {s.id for s in seats}
    return ChartRead(
        teams=[TeamRead.model_validate(t) for t in teams],
        seats=[_seat_read(s) for s in seats],
        edges=[
            ChartEdge(from_id=s.reports_to_id, to_id=s.id)
            for s in seats
            if s.reports_to_id and s.reports_to_id in visible
        ],
        constitution_md=project.constitution_md or DEFAULT_CONSTITUTION_MD,
    )


@router.get("/projects/{project_id}/org/export.yaml")
async def export_yaml(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> PlainTextResponse:
    principal.require_scope("org:read")
    teams, seats = await list_chart(session, project)
    body = export_multi_team_yaml(teams, seats)
    return PlainTextResponse(body, media_type="text/yaml")


@router.get("/projects/{project_id}/roster/agents")
async def roster_agents(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
) -> dict:
    """Starter roster as OpenCode harness-pack agents (deny-by-default tools)."""
    principal.require_scope("org:read")
    return {"project_id": str(project.id), "agents": starter_agent_pack()}


@router.get("/projects/{project_id}/constitution", response_model=ConstitutionRead)
async def get_constitution(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> ConstitutionRead:
    principal.require_scope("org:read")
    if not (project.constitution_md or "").strip():
        project.constitution_md = DEFAULT_CONSTITUTION_MD
        await session.commit()
    return ConstitutionRead(constitution_md=project.constitution_md or DEFAULT_CONSTITUTION_MD)


@router.put("/projects/{project_id}/constitution", response_model=ConstitutionRead)
async def put_constitution(
    body: ConstitutionUpdate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> ConstitutionRead:
    principal.require_scope("org:rw")
    project.constitution_md = body.constitution_md
    await session.commit()
    return ConstitutionRead(constitution_md=project.constitution_md or "")


@router.get("/projects/{project_id}/teams", response_model=list[TeamRead])
async def list_teams(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[Team]:
    principal.require_scope("org:read")
    result = await session.execute(
        select(Team).where(Team.project_id == project.id).order_by(Team.name)
    )
    return list(result.scalars().all())


@router.post(
    "/projects/{project_id}/teams",
    response_model=TeamRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_team(
    body: TeamCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> Team:
    principal.require_scope("org:rw")
    team = Team(
        project_id=project.id,
        name=body.name.strip(),
        slug=body.slug,
        mention=(body.mention or body.slug).strip().lstrip("@"),
        lane=body.lane,
        description=body.description,
    )
    session.add(team)
    await session.commit()
    await session.refresh(team)
    return team


@router.patch("/projects/{project_id}/teams/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: UUID,
    body: TeamUpdate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> Team:
    principal.require_scope("org:rw")
    team = await session.get(Team, team_id)
    if team is None or team.project_id != project.id:
        raise HTTPException(status_code=404, detail="Team not found")
    if body.name is not None:
        team.name = body.name
    if body.mention is not None:
        team.mention = body.mention.lstrip("@")
    if body.lane is not None:
        team.lane = body.lane
    if body.description is not None:
        team.description = body.description
    if body.conductor_seat_id is not None:
        team.conductor_seat_id = body.conductor_seat_id
    await session.commit()
    await session.refresh(team)
    return team


@router.delete("/projects/{project_id}/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("org:rw")
    team = await session.get(Team, team_id)
    if team is None or team.project_id != project.id:
        raise HTTPException(status_code=404, detail="Team not found")
    assigned = await session.scalar(
        select(Seat.id).where(
            Seat.project_id == project.id,
            Seat.team_id == team_id,
            Seat.fired.is_(False),
        ).limit(1)
    )
    if assigned is not None:
        raise HTTPException(
            status_code=409,
            detail="Remove or reassign seats on this team before deleting it",
        )
    await session.delete(team)
    await session.commit()


@router.get("/projects/{project_id}/seats", response_model=list[SeatRead])
async def list_seats(
    include_system: bool = Query(default=False),
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[SeatRead]:
    principal.require_scope("org:read")
    result = await session.execute(
        select(Seat).where(Seat.project_id == project.id).order_by(Seat.name)
    )
    seats = list(result.scalars().all())
    return [_seat_read(s) for s in _filter_seats(seats, include_system)]


@router.post(
    "/projects/{project_id}/seats",
    response_model=SeatRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_seat(
    body: SeatCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> SeatRead:
    principal.require_scope("org:rw")
    defaults = hire_defaults(body.template) if body.template else {}
    slug = body.slug or defaults.get("slug") or body.name.lower().replace(" ", "-")
    seat = Seat(
        project_id=project.id,
        team_id=body.team_id,
        kind=body.kind,
        slug=slug,
        name=body.name.strip(),
        role=body.role or defaults.get("role") or "specialist",
        lane=body.lane or defaults.get("lane") or "line",
        description=body.description or defaults.get("description") or "",
        reports_to_id=body.reports_to_id,
        owner_user_id=principal.user.id,
        agent_slug=body.agent_slug or defaults.get("agent_slug"),
        is_conductor=body.is_conductor,
        worktree_path=body.worktree_path or defaults.get("worktree_path"),
        budget_tokens=body.budget_tokens,
        permission=body.permission or defaults.get("permission") or {},
        tools=list(body.tools or defaults.get("tools") or []),
        prompt=body.prompt or defaults.get("prompt") or "",
        skills=list(body.skills or defaults.get("skills") or []),
        preferred_models=list(body.preferred_models or defaults.get("preferred_models") or []),
    )
    session.add(seat)
    await session.commit()
    await session.refresh(seat)
    return _seat_read(seat)


@router.get("/projects/{project_id}/seats/{seat_id}", response_model=SeatRead)
async def get_seat(
    seat_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> SeatRead:
    principal.require_scope("org:read")
    return _seat_read(await _get_seat(session, project.id, seat_id))


@router.patch("/projects/{project_id}/seats/{seat_id}", response_model=SeatRead)
async def update_seat(
    seat_id: UUID,
    body: SeatUpdate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> SeatRead:
    principal.require_scope("org:rw")
    seat = await _get_seat(session, project.id, seat_id)
    data = body.model_dump(exclude_unset=True)
    reports_changed = "reports_to_id" in data
    new_parent = data.pop("reports_to_id", None) if reports_changed else None
    for key, value in data.items():
        setattr(seat, key, value)
    if reports_changed:
        result = await session.execute(select(Seat).where(Seat.project_id == project.id))
        all_seats = list(result.scalars().all())
        if new_parent is not None:
            parent = next((s for s in all_seats if s.id == new_parent), None)
            if parent is None:
                raise HTTPException(status_code=400, detail="Parent seat not found")
            if parent.fired:
                raise HTTPException(status_code=400, detail="Cannot report to a removed seat")
        if would_cycle(all_seats, seat.id, new_parent):
            raise HTTPException(
                status_code=400, detail="Reports-to would create a reporting cycle"
            )
        seat.reports_to_id = new_parent
    await session.commit()
    await session.refresh(seat)
    try:
        from app.services.session_bind import sync_seat_to_harness

        await sync_seat_to_harness(project, seat, get_settings())
    except Exception as exc:  # noqa: BLE001
        logger.info("harness sync after seat patch failed seat=%s: %s", seat.slug, exc)
    return _seat_read(seat)


@router.post("/projects/{project_id}/seats/{seat_id}/reparent", response_model=SeatRead)
async def reparent(
    seat_id: UUID,
    body: SeatReparent,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> SeatRead:
    principal.require_scope("org:rw")
    seat = await _get_seat(session, project.id, seat_id)
    try:
        seat = await reparent_seat(session, project, seat, body.reports_to_id)
    except OrgGraphError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _seat_read(seat)


@router.post("/projects/{project_id}/seats/{seat_id}/attach", response_model=SeatRead)
async def attach(
    seat_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> SeatRead:
    principal.require_scope("org:rw")
    seat = await _get_seat(session, project.id, seat_id)
    try:
        seat = await attach_seat_session(session, project, seat, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _seat_read(seat)


@router.post("/projects/{project_id}/seats/{seat_id}/pause", response_model=SeatRead)
async def pause(
    seat_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> SeatRead:
    principal.require_scope("org:rw")
    seat = await _get_seat(session, project.id, seat_id)
    return _seat_read(await pause_seat(session, seat))


@router.post("/projects/{project_id}/seats/{seat_id}/resume", response_model=SeatRead)
async def resume(
    seat_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> SeatRead:
    principal.require_scope("org:rw")
    seat = await _get_seat(session, project.id, seat_id)
    try:
        return _seat_read(await resume_seat(session, seat))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/projects/{project_id}/seats/{seat_id}/fire", response_model=SeatRead)
async def fire(
    seat_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> SeatRead:
    principal.require_scope("org:rw")
    seat = await _get_seat(session, project.id, seat_id)
    return _seat_read(await fire_seat(session, seat))
