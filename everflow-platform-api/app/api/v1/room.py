"""Room: channels, messages, threads, @team mentions."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal, get_principal, get_project_for_principal
from app.db.session import get_async_session
from app.models.bus import OrgRun
from app.models.org import Seat, Team
from app.models.project import Project
from app.models.room import Channel, ChannelMessage
from app.schemas.bus import RunRead
from app.schemas.room import ChannelCreate, ChannelMessageCreate, ChannelMessageRead, ChannelRead
from app.services.conductor import compile_run, looks_like_ship_train, parse_mentions
from app.services.org_graph import ensure_starter_company
from app.services.run_read import run_read

router = APIRouter(tags=["room"])


def _msg_read(row: ChannelMessage) -> ChannelMessageRead:
    data = ChannelMessageRead.model_validate(row)
    data.mentions = list(row.mentions or [])
    return data


@router.get("/projects/{project_id}/channels", response_model=list[ChannelRead])
async def list_channels(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[Channel]:
    principal.require_scope("room:read")
    result = await session.execute(
        select(Channel).where(Channel.project_id == project.id).order_by(Channel.slug)
    )
    rows = list(result.scalars().all())
    if not rows:
        await ensure_starter_company(session, project, owner=principal.user)
        result = await session.execute(
            select(Channel).where(Channel.project_id == project.id).order_by(Channel.slug)
        )
        rows = list(result.scalars().all())
    return rows


@router.post(
    "/projects/{project_id}/channels",
    response_model=ChannelRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel(
    body: ChannelCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> Channel:
    principal.require_scope("room:rw")
    ch = Channel(
        project_id=project.id,
        slug=body.slug,
        name=body.name.strip().lstrip("#"),
        kind=body.kind,
        team_id=body.team_id,
    )
    session.add(ch)
    await session.commit()
    await session.refresh(ch)
    return ch


@router.delete(
    "/projects/{project_id}/channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_channel(
    channel_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("room:rw")
    ch = await session.get(Channel, channel_id)
    if ch is None or ch.project_id != project.id:
        raise HTTPException(status_code=404, detail="Channel not found")
    await session.delete(ch)
    await session.commit()


@router.get(
    "/projects/{project_id}/channels/{channel_id}/messages",
    response_model=list[ChannelMessageRead],
)
async def list_messages(
    channel_id: UUID,
    thread_id: UUID | None = Query(default=None),
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[ChannelMessageRead]:
    principal.require_scope("room:read")
    ch = await session.get(Channel, channel_id)
    if ch is None or ch.project_id != project.id:
        raise HTTPException(status_code=404, detail="Channel not found")
    q = select(ChannelMessage).where(ChannelMessage.channel_id == channel_id)
    if thread_id:
        q = q.where(
            (ChannelMessage.thread_id == thread_id) | (ChannelMessage.id == thread_id)
        )
    else:
        q = q.where(ChannelMessage.thread_id.is_(None))
    q = q.order_by(ChannelMessage.created_at.asc())
    return [_msg_read(m) for m in (await session.execute(q)).scalars().all()]


@router.post(
    "/projects/{project_id}/channels/{channel_id}/messages",
    response_model=ChannelMessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    channel_id: UUID,
    body: ChannelMessageCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> ChannelMessageRead:
    principal.require_scope("room:rw")
    ch = await session.get(Channel, channel_id)
    if ch is None or ch.project_id != project.id:
        raise HTTPException(status_code=404, detail="Channel not found")

    mentions = parse_mentions(body.body)
    # Resolve @team to team slugs present on the project
    teams = {
        t.mention: t
        for t in (
            await session.execute(select(Team).where(Team.project_id == project.id))
        ).scalars().all()
    }
    seats = {
        s.slug: s
        for s in (
            await session.execute(select(Seat).where(Seat.project_id == project.id))
        ).scalars().all()
    }
    resolved: list[dict] = []
    for m in mentions:
        if m["slug"] in teams:
            resolved.append({"kind": "team", "slug": m["slug"], "id": str(teams[m["slug"]].id)})
        elif m["slug"] in seats:
            resolved.append({"kind": "seat", "slug": m["slug"], "id": str(seats[m["slug"]].id)})
        else:
            resolved.append(m)

    should_compile = body.compile_run or looks_like_ship_train(body.body)
    run_id = None
    if should_compile:
        # Need seats/teams seeded
        seat_count = await session.scalar(
            select(Seat.id).where(Seat.project_id == project.id).limit(1)
        )
        if seat_count is None:
            await ensure_starter_company(session, project, owner=principal.user)

    msg = ChannelMessage(
        channel_id=ch.id,
        thread_id=body.thread_id,
        author_user_id=principal.user.id,
        author_seat_id=body.author_seat_id,
        body=body.body,
        kind="message",
        mentions=resolved,
    )
    session.add(msg)
    await session.flush()

    if should_compile:
        run = await compile_run(
            session,
            project,
            sentence=body.body,
            channel_id=ch.id,
            thread_id=body.thread_id or msg.id,
            created_by=principal.user,
            start=True,
            commit=False,
        )
        run_id = run.id
        msg.run_id = run_id
        # Thread = audit log: attach a run card system message
        session.add(
            ChannelMessage(
                channel_id=ch.id,
                thread_id=body.thread_id or msg.id,
                author_seat_id=seats.get("floor").id if seats.get("floor") else None,
                body=f"Floor compiled run `{run.title}`",
                kind="run_event",
                mentions=[],
                run_id=run.id,
            )
        )

    await session.commit()
    await session.refresh(msg)
    return _msg_read(msg)


@router.get("/projects/{project_id}/runs", response_model=list[RunRead])
async def list_runs(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[RunRead]:
    principal.require_scope("room:read")
    result = await session.execute(
        select(OrgRun).where(OrgRun.project_id == project.id).order_by(OrgRun.created_at.desc())
    )
    runs = list(result.scalars().all())
    out: list[RunRead] = []
    for run in runs:
        out.append(await run_read(session, run))
    return out


@router.get("/projects/{project_id}/runs/{run_id}", response_model=RunRead)
async def get_run(
    run_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> RunRead:
    principal.require_scope("room:read")
    run = await session.get(OrgRun, run_id)
    if run is None or run.project_id != project.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return await run_read(session, run)
