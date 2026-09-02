"""Ensure starter company, chart ops, reporting-line walks, constitution."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.starter_roster import (
    DEFAULT_CONSTITUTION_MD,
    STARTER_CHANNELS,
    STARTER_SEATS,
    STARTER_TEAMS,
    seat_by_slug,
)
from app.models.org import Seat, Team
from app.models.project import Project
from app.models.room import Channel
from app.models.user import User

logger = logging.getLogger(__name__)


class OrgGraphError(ValueError):
    pass


async def _teams_by_slug(session: AsyncSession, project_id: UUID) -> dict[str, Team]:
    result = await session.execute(select(Team).where(Team.project_id == project_id))
    return {t.slug: t for t in result.scalars().all()}


async def _seats_by_slug(session: AsyncSession, project_id: UUID) -> dict[str, Seat]:
    result = await session.execute(select(Seat).where(Seat.project_id == project_id))
    return {s.slug: s for s in result.scalars().all()}


async def ensure_starter_company(
    session: AsyncSession,
    project: Project,
    *,
    owner: User | None = None,
) -> tuple[list[Team], list[Seat], list[Channel]]:
    """Idempotently seed teams, seats, #ship, and constitution."""
    if not (project.constitution_md or "").strip():
        project.constitution_md = DEFAULT_CONSTITUTION_MD

    teams = await _teams_by_slug(session, project.id)
    for spec in STARTER_TEAMS:
        if spec["slug"] in teams:
            continue
        team = Team(
            project_id=project.id,
            name=spec["name"],
            slug=spec["slug"],
            mention=spec["mention"],
            lane=spec["lane"],
            description=spec.get("description") or "",
        )
        session.add(team)
        await session.flush()
        teams[team.slug] = team

    seats = await _seats_by_slug(session, project.id)
    created: list[Seat] = []
    for spec in STARTER_SEATS:
        if spec["slug"] in seats:
            existing = seats[spec["slug"]]
            if not (existing.prompt or "").strip() and spec.get("prompt"):
                existing.prompt = spec["prompt"]
            if not existing.skills and spec.get("skills"):
                existing.skills = list(spec["skills"])
            if not existing.preferred_models and spec.get("preferred_models"):
                existing.preferred_models = list(spec["preferred_models"])
            continue
        team = teams.get(spec["team"]) if spec.get("team") else None
        seat = Seat(
            project_id=project.id,
            team_id=team.id if team else None,
            kind=spec["kind"],
            slug=spec["slug"],
            name=spec["name"],
            role=spec["role"],
            lane=spec["lane"],
            description=spec.get("description") or "",
            agent_slug=spec.get("agent_slug"),
            is_conductor=bool(spec.get("is_conductor")),
            worktree_path=spec.get("worktree_path"),
            permission=dict(spec.get("permission") or {}),
            tools=list(spec.get("tools") or []),
            prompt=spec.get("prompt") or "",
            skills=list(spec.get("skills") or []),
            preferred_models=list(spec.get("preferred_models") or []),
            owner_user_id=owner.id if owner and spec["kind"] == "human" else (
                owner.id if owner else None
            ),
            status="idle",
        )
        session.add(seat)
        await session.flush()
        seats[seat.slug] = seat
        created.append(seat)

    # Resolve reports_to after all seats exist
    for spec in STARTER_SEATS:
        parent_slug = spec.get("reports_to")
        child = seats.get(spec["slug"])
        if child is None:
            continue
        if parent_slug:
            parent = seats.get(parent_slug)
            if parent and child.reports_to_id != parent.id:
                child.reports_to_id = parent.id
        if spec.get("is_conductor"):
            # Floor is the default conductor for line teams that have none
            for team in teams.values():
                if team.lane == "line" and team.conductor_seat_id is None:
                    team.conductor_seat_id = child.id

    result = await session.execute(select(Channel).where(Channel.project_id == project.id))
    channels = {c.slug: c for c in result.scalars().all()}
    for spec in STARTER_CHANNELS:
        if spec["slug"] in channels:
            continue
        ch = Channel(
            project_id=project.id,
            slug=spec["slug"],
            name=spec["name"],
            kind=spec["kind"],
        )
        session.add(ch)
        await session.flush()
        channels[ch.slug] = ch

    await session.commit()
    await session.refresh(project)
    team_list = list((await _teams_by_slug(session, project.id)).values())
    seat_list = list((await _seats_by_slug(session, project.id)).values())
    ch_result = await session.execute(select(Channel).where(Channel.project_id == project.id))
    return team_list, seat_list, list(ch_result.scalars().all())


def would_cycle(seats: list[Seat], seat_id: UUID, new_parent_id: UUID | None) -> bool:
    if new_parent_id is None:
        return False
    if new_parent_id == seat_id:
        return True
    by_id = {s.id: s for s in seats}
    seen: set[UUID] = {seat_id}
    cur = new_parent_id
    while cur is not None:
        if cur in seen:
            return True
        seen.add(cur)
        parent = by_id.get(cur)
        cur = parent.reports_to_id if parent else None
    return False


async def reparent_seat(
    session: AsyncSession,
    project: Project,
    seat: Seat,
    new_parent_id: UUID | None,
) -> Seat:
    result = await session.execute(select(Seat).where(Seat.project_id == project.id))
    seats = list(result.scalars().all())
    if new_parent_id is not None:
        parent = next((s for s in seats if s.id == new_parent_id), None)
        if parent is None:
            raise OrgGraphError("Parent seat not found")
        if parent.fired:
            raise OrgGraphError("Cannot report to a fired seat")
    if would_cycle(seats, seat.id, new_parent_id):
        raise OrgGraphError("Reparent would create a reporting cycle")
    seat.reports_to_id = new_parent_id
    await session.commit()
    await session.refresh(seat)
    return seat


async def walk_reports_to_human(
    session: AsyncSession,
    project: Project,
    from_seat: Seat,
) -> Seat | None:
    """Walk reports_to until a human (unfired) seat is found. Never #general."""
    result = await session.execute(select(Seat).where(Seat.project_id == project.id))
    by_id = {s.id: s for s in result.scalars().all()}
    seen: set[UUID] = set()
    cur: Seat | None = from_seat
    while cur is not None:
        if cur.id in seen:
            break
        seen.add(cur.id)
        if cur.kind == "human" and not cur.fired:
            return cur
        nxt_id = cur.reports_to_id
        cur = by_id.get(nxt_id) if nxt_id else None
    # Fallback: any human board seat on the project
    for s in by_id.values():
        if s.kind == "human" and not s.fired:
            return s
    return None


async def list_chart(
    session: AsyncSession,
    project: Project,
    *,
    include_system: bool = True,
) -> tuple[list[Team], list[Seat]]:
    teams = list(
        (
            await session.execute(
                select(Team).where(Team.project_id == project.id).order_by(Team.lane, Team.name)
            )
        ).scalars().all()
    )
    q = select(Seat).where(Seat.project_id == project.id, Seat.fired.is_(False))
    if not include_system:
        q = q.where(Seat.is_conductor.is_(False))
    seats = list((await session.execute(q.order_by(Seat.lane, Seat.name))).scalars().all())
    return teams, seats


def export_multi_team_yaml(teams: list[Team], seats: list[Seat]) -> str:
    lines = ["# Everflow org export — git-versioned topology", "teams:"]
    by_team: dict[UUID | None, list[Seat]] = {}
    for s in seats:
        by_team.setdefault(s.team_id, []).append(s)
    for team in teams:
        lines.append(f"  - slug: {team.slug}")
        lines.append(f"    name: {team.name}")
        lines.append(f"    mention: '@{team.mention}'")
        lines.append(f"    lane: {team.lane}")
        lines.append("    seats:")
        for s in by_team.get(team.id, []):
            parent = next((p.slug for p in seats if p.id == s.reports_to_id), None)
            lines.append(f"      - slug: {s.slug}")
            lines.append(f"        name: {s.name}")
            lines.append(f"        kind: {s.kind}")
            lines.append(f"        role: {s.role}")
            if s.agent_slug:
                lines.append(f"        agent: {s.agent_slug}")
            if parent:
                lines.append(f"        reports_to: {parent}")
            if s.worktree_path:
                lines.append(f"        worktree: {s.worktree_path}")
    unteamed = by_team.get(None, [])
    if unteamed:
        lines.append("unassigned:")
        for s in unteamed:
            parent = next((p.slug for p in seats if p.id == s.reports_to_id), None)
            lines.append(f"  - slug: {s.slug}")
            lines.append(f"    name: {s.name}")
            lines.append(f"    kind: {s.kind}")
            lines.append(f"    role: {s.role}")
            if parent:
                lines.append(f"    reports_to: {parent}")
    return "\n".join(lines) + "\n"


def hire_defaults(template: str) -> dict:
    """Template slug → starter spec fields for hire-from-chart."""
    try:
        return dict(seat_by_slug(template))
    except KeyError:
        return {
            "slug": template,
            "name": template.replace("-", " ").title(),
            "kind": "bot",
            "role": "specialist",
            "lane": "line",
            "team": None,
            "reports_to": "floor",
            "agent_slug": template,
            "is_conductor": False,
            "worktree_path": None,
            "permission": {"read": "allow", "edit": "deny", "bash": "deny"},
            "tools": ["read"],
            "prompt": "",
            "skills": [],
            "preferred_models": [],
            "description": "",
        }
