"""Load run nodes without lazy-loading the ORM relationship."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bus import OrgRun, OrgRunNode
from app.schemas.bus import RunRead


async def load_run_nodes(session: AsyncSession, run_id: UUID) -> list[OrgRunNode]:
    result = await session.execute(
        select(OrgRunNode).where(OrgRunNode.run_id == run_id).order_by(OrgRunNode.sort_order)
    )
    return list(result.scalars().all())


async def run_read(session: AsyncSession, run: OrgRun) -> RunRead:
    nodes = await load_run_nodes(session, run.id)
    return RunRead(
        id=run.id,
        project_id=run.project_id,
        channel_id=run.channel_id,
        thread_id=run.thread_id,
        title=run.title,
        sentence=run.sentence,
        status=run.status,
        compiled_graph=dict(run.compiled_graph or {}),
        created_by=run.created_by,
        created_at=run.created_at,
        updated_at=run.updated_at,
        nodes=nodes,
    )
