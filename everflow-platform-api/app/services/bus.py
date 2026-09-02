"""Audited bot bus: verbs, rate limit, cycle detector, ask_human walk."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bus import BusEvent, MemoryBlock, OrgRun, OrgRunNode
from app.models.org import Seat
from app.models.project import Project
from app.models.room import Channel, ChannelMessage
from app.services.org_graph import walk_reports_to_human

BUS_VERBS = {
    "send_message",
    "handoff",
    "share_memory",
    "create_task",
    "depend_on",
    "ask_human",
    "report",
}

_RATE_LIMIT = 60
_RATE_WINDOW = timedelta(minutes=1)


class BusError(ValueError):
    pass


async def _rate_limited(session: AsyncSession, project_id: UUID) -> bool:
    since = datetime.now(timezone.utc) - _RATE_WINDOW
    count = await session.scalar(
        select(func.count()).select_from(BusEvent).where(
            BusEvent.project_id == project_id,
            BusEvent.created_at >= since,
        )
    )
    return int(count or 0) >= _RATE_LIMIT


async def _cycle_on_run(
    session: AsyncSession,
    run_id: UUID | None,
    from_seat_id: UUID | None,
    to_seat_id: UUID | None,
) -> bool:
    """True if adding from→to would close a message/handoff cycle on this run."""
    if not run_id or not from_seat_id or not to_seat_id:
        return False
    if from_seat_id == to_seat_id:
        return True
    result = await session.execute(
        select(BusEvent).where(
            BusEvent.run_id == run_id,
            BusEvent.verb.in_(("send_message", "handoff")),
            BusEvent.status == "ok",
        )
    )
    edges: dict[UUID, list[UUID]] = defaultdict(list)
    for ev in result.scalars().all():
        if ev.from_seat_id and ev.to_seat_id:
            edges[ev.from_seat_id].append(ev.to_seat_id)
    # Would-be edge
    q: deque[UUID] = deque([to_seat_id])
    seen: set[UUID] = set()
    while q:
        cur = q.popleft()
        if cur == from_seat_id:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        q.extend(edges.get(cur, []))
    return False


async def dispatch(
    session: AsyncSession,
    project: Project,
    *,
    verb: str,
    from_seat_id: UUID | None = None,
    to_seat_id: UUID | None = None,
    to_team_id: UUID | None = None,
    to_channel_id: UUID | None = None,
    run_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> BusEvent:
    if verb not in BUS_VERBS:
        raise BusError(f"Unknown bus verb: {verb}")
    if await _rate_limited(session, project.id):
        raise BusError("Bus rate limit exceeded")

    payload = dict(payload or {})

    if from_seat_id:
        from_seat = await session.get(Seat, from_seat_id)
        if from_seat is None or from_seat.project_id != project.id:
            raise BusError("from_seat not found")
        if from_seat.paused or from_seat.fired:
            raise BusError("from_seat is paused or fired")
    else:
        from_seat = None

    if verb in ("send_message", "handoff") and await _cycle_on_run(
        session, run_id, from_seat_id, to_seat_id
    ):
        ev = BusEvent(
            project_id=project.id,
            run_id=run_id,
            verb=verb,
            from_seat_id=from_seat_id,
            to_seat_id=to_seat_id,
            to_team_id=to_team_id,
            to_channel_id=to_channel_id,
            payload=payload,
            status="cycle_blocked",
            error="Cycle detector stopped a loop",
        )
        session.add(ev)
        await session.commit()
        await session.refresh(ev)
        return ev

    human_seat: Seat | None = None
    if verb == "ask_human":
        if from_seat is None:
            raise BusError("ask_human requires from_seat_id")
        human_seat = await walk_reports_to_human(session, project, from_seat)
        if human_seat is None:
            raise BusError("No human manager on reports_to chain")
        to_seat_id = human_seat.id
        payload = {
            **payload,
            "escalated_to": human_seat.slug,
            "note": "ask_human walks reports_to; never dumps to #general",
        }
        if run_id:
            run = await session.get(OrgRun, run_id)
            if run and run.project_id == project.id:
                run.status = "blocked"

    if verb == "share_memory":
        scope = str(payload.get("scope") or "project")
        scope_id = str(payload.get("scope_id") or "")
        name = str(payload.get("name") or "").strip()
        body = str(payload.get("body") or "")
        if not name:
            raise BusError("share_memory requires payload.name")
        existing = await session.execute(
            select(MemoryBlock).where(
                MemoryBlock.project_id == project.id,
                MemoryBlock.scope == scope,
                MemoryBlock.scope_id == scope_id,
                MemoryBlock.name == name,
            )
        )
        block = existing.scalar_one_or_none()
        if block is None:
            session.add(
                MemoryBlock(
                    project_id=project.id,
                    scope=scope,
                    scope_id=scope_id,
                    name=name,
                    body=body,
                )
            )
        else:
            block.body = body

    if verb == "depend_on" and run_id:
        node_key = str(payload.get("node") or "")
        depends = payload.get("depends_on") or []
        if node_key and isinstance(depends, list):
            node = (
                await session.execute(
                    select(OrgRunNode).where(
                        OrgRunNode.run_id == run_id, OrgRunNode.key == node_key
                    )
                )
            ).scalar_one_or_none()
            if node:
                node.depends_on = [str(x) for x in depends]

    if verb == "create_task" and run_id:
        node_key = str(payload.get("key") or payload.get("name") or "task")
        label = str(payload.get("label") or node_key)
        session.add(
            OrgRunNode(
                run_id=run_id,
                seat_id=to_seat_id,
                key=node_key,
                label=label,
                status="waiting",
                brief=str(payload.get("brief") or ""),
                sort_order=99,
                depends_on=list(payload.get("depends_on") or []),
            )
        )

    if verb == "handoff" and run_id:
        if from_seat_id:
            for node in (
                await session.execute(
                    select(OrgRunNode).where(
                        OrgRunNode.run_id == run_id, OrgRunNode.seat_id == from_seat_id
                    )
                )
            ).scalars().all():
                if node.status in ("waiting", "running"):
                    node.status = "done"
        if to_seat_id:
            nxt = (
                await session.execute(
                    select(OrgRunNode).where(
                        OrgRunNode.run_id == run_id, OrgRunNode.seat_id == to_seat_id
                    )
                )
            ).scalars().first()
            if nxt and nxt.status == "waiting":
                nxt.status = "running"

    if verb == "report" and run_id:
        run = await session.get(OrgRun, run_id)
        result_text = str(payload.get("result") or payload.get("body") or "")
        ok = payload.get("ok", True)
        if from_seat_id:
            for node in (
                await session.execute(
                    select(OrgRunNode).where(
                        OrgRunNode.run_id == run_id, OrgRunNode.seat_id == from_seat_id
                    )
                )
            ).scalars().all():
                node.status = "done" if ok else "failed"
                node.result = result_text
        if run and run.project_id == project.id:
            remaining = (
                await session.execute(
                    select(OrgRunNode).where(
                        OrgRunNode.run_id == run_id,
                        OrgRunNode.status.in_(("waiting", "running", "blocked")),
                    )
                )
            ).scalars().all()
            if not remaining:
                run.status = "done" if ok else "failed"

    # Audit note in the originating channel when possible
    if to_channel_id or (run_id and verb in ("ask_human", "report", "handoff", "send_message")):
        channel_id = to_channel_id
        if channel_id is None and run_id:
            run = await session.get(OrgRun, run_id)
            channel_id = run.channel_id if run else None
        if channel_id:
            ch = await session.get(Channel, channel_id)
            if ch and ch.project_id == project.id:
                session.add(
                    ChannelMessage(
                        channel_id=ch.id,
                        thread_id=None,
                        author_seat_id=from_seat_id,
                        body=_event_body(verb, payload, human_seat),
                        kind="run_event",
                        run_id=run_id,
                        mentions=[],
                    )
                )

    ev = BusEvent(
        project_id=project.id,
        run_id=run_id,
        verb=verb,
        from_seat_id=from_seat_id,
        to_seat_id=to_seat_id,
        to_team_id=to_team_id,
        to_channel_id=to_channel_id,
        payload=payload,
        status="ok",
    )
    session.add(ev)
    await session.commit()
    await session.refresh(ev)
    return ev


def _event_body(verb: str, payload: dict[str, Any], human: Seat | None) -> str:
    if verb == "ask_human" and human:
        return f"ask_human → @{human.slug} (walked reports_to). {payload.get('reason') or payload.get('body') or ''}".strip()
    if verb == "handoff":
        return f"handoff: {payload.get('brief') or payload.get('body') or 'phase closed'}"
    if verb == "report":
        return f"report: {payload.get('result') or payload.get('body') or ''}".strip()
    if verb == "send_message":
        return str(payload.get("body") or payload.get("text") or "message")
    return f"{verb}: {payload.get('body') or ''}".strip()


async def list_events(
    session: AsyncSession,
    project: Project,
    *,
    run_id: UUID | None = None,
    limit: int = 100,
) -> list[BusEvent]:
    q = select(BusEvent).where(BusEvent.project_id == project.id)
    if run_id:
        q = q.where(BusEvent.run_id == run_id)
    q = q.order_by(BusEvent.created_at.desc()).limit(limit)
    return list((await session.execute(q)).scalars().all())
