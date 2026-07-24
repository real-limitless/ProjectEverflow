"""AI usage ingest (project) and summary (org) APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import current_active_user
from app.core.deps import get_org_membership, get_project_for_member
from app.db.session import get_async_session
from app.models.organization import OrganizationMember
from app.models.project import Project
from app.models.user import User
from app.schemas.ai_usage import (
    AiUsageBatchResult,
    AiUsageEventBatchCreate,
    AiUsageEventCreate,
    AiUsageEventRead,
    AiUsageSummary,
)
from app.services.ai_usage import (
    build_usage_summary,
    upsert_usage_event,
    upsert_usage_events_batch,
)

router = APIRouter(tags=["usage"])


@router.post(
    "/projects/{project_id}/usage/events",
    response_model=AiUsageEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_usage_event(
    body: AiUsageEventCreate,
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> AiUsageEventRead:
    row = await upsert_usage_event(
        session,
        project=project,
        user_id=user.id,
        body=body,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Event has no token usage and is not marked completed",
        )
    return AiUsageEventRead.model_validate(row)


@router.post(
    "/projects/{project_id}/usage/events/batch",
    response_model=AiUsageBatchResult,
)
async def create_usage_events_batch(
    body: AiUsageEventBatchCreate,
    project: Project = Depends(get_project_for_member),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> AiUsageBatchResult:
    accepted, skipped = await upsert_usage_events_batch(
        session,
        project=project,
        user_id=user.id,
        events=body.events,
    )
    return AiUsageBatchResult(
        accepted=len(accepted),
        skipped=skipped,
        events=[AiUsageEventRead.model_validate(r) for r in accepted],
    )


@router.get("/orgs/{org_id}/usage/summary", response_model=AiUsageSummary)
async def get_usage_summary(
    scope: Literal["me", "org"] = Query(default="me"),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    project_id: UUID | None = Query(default=None),
    membership: OrganizationMember = Depends(get_org_membership),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> AiUsageSummary:
    now = datetime.now(timezone.utc)
    to_dt = to or now
    from_dt = from_ or (to_dt - timedelta(days=30))
    if from_dt > to_dt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="'from' must be before or equal to 'to'",
        )
    # Cap range to 366 days to keep aggregates cheap.
    if (to_dt - from_dt) > timedelta(days=366):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Date range must be at most 366 days",
        )

    return await build_usage_summary(
        session,
        organization_id=membership.organization_id,
        scope=scope,
        current_user_id=user.id,
        from_dt=from_dt,
        to_dt=to_dt,
        project_id=project_id,
    )
