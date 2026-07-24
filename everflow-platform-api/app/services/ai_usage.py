"""Ingest and aggregate AI chat usage events."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.models.ai_usage import AiUsageEvent
from app.models.project import Project
from app.models.user import User
from app.schemas.ai_usage import (
    AiUsageByModel,
    AiUsageByProject,
    AiUsageByUser,
    AiUsageDailyPoint,
    AiUsageEventCreate,
    AiUsageSummary,
    AiUsageTotals,
)


def _token_sum(body: AiUsageEventCreate) -> int:
    return (
        body.input_tokens
        + body.output_tokens
        + body.reasoning_tokens
        + body.cache_read_tokens
        + body.cache_write_tokens
    )


def should_accept_event(body: AiUsageEventCreate) -> bool:
    """Skip empty noise unless the client marks the turn completed."""
    total = body.total_tokens or 0
    if total > 0 or _token_sum(body) > 0:
        return True
    return bool(body.completed)


def _effective_total(body: AiUsageEventCreate) -> int:
    if body.total_tokens and body.total_tokens > 0:
        return body.total_tokens
    return _token_sum(body)


def _event_is_richer(existing: AiUsageEvent, body: AiUsageEventCreate) -> bool:
    """Prefer reports with more complete token totals / model metadata."""
    new_total = _effective_total(body)
    if new_total > existing.total_tokens:
        return True
    if new_total == existing.total_tokens:
        if body.provider and not existing.provider:
            return True
        if body.model and not existing.model:
            return True
        if body.duration_ms is not None and existing.duration_ms is None:
            return True
        if body.ttft_ms is not None and existing.ttft_ms is None:
            return True
    return False


def _apply_body(row: AiUsageEvent, body: AiUsageEventCreate, *, occurred_at: datetime) -> None:
    row.session_id = body.session_id
    row.provider = body.provider
    row.model = body.model
    row.input_tokens = body.input_tokens
    row.output_tokens = body.output_tokens
    row.reasoning_tokens = body.reasoning_tokens
    row.cache_read_tokens = body.cache_read_tokens
    row.cache_write_tokens = body.cache_write_tokens
    row.total_tokens = _effective_total(body)
    row.duration_ms = body.duration_ms
    row.ttft_ms = body.ttft_ms
    row.occurred_at = occurred_at


async def upsert_usage_event(
    session: AsyncSession,
    *,
    project: Project,
    user_id: UUID,
    body: AiUsageEventCreate,
) -> AiUsageEvent | None:
    if not should_accept_event(body):
        return None

    occurred_at = body.occurred_at or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)

    result = await session.execute(
        select(AiUsageEvent).where(AiUsageEvent.message_id == body.message_id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        # Do not let another project/user hijack a message_id.
        if existing.project_id != project.id:
            return existing
        if _event_is_richer(existing, body):
            _apply_body(existing, body, occurred_at=occurred_at)
            await session.commit()
            await session.refresh(existing)
        return existing

    row = AiUsageEvent(
        organization_id=project.organization_id,
        project_id=project.id,
        user_id=user_id,
        message_id=body.message_id,
    )
    _apply_body(row, body, occurred_at=occurred_at)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def upsert_usage_events_batch(
    session: AsyncSession,
    *,
    project: Project,
    user_id: UUID,
    events: list[AiUsageEventCreate],
) -> tuple[list[AiUsageEvent], int]:
    accepted: list[AiUsageEvent] = []
    skipped = 0
    for body in events:
        row = await upsert_usage_event(
            session,
            project=project,
            user_id=user_id,
            body=body,
        )
        if row is None:
            skipped += 1
        else:
            accepted.append(row)
    return accepted, skipped


def _scope_filters(
    *,
    organization_id: UUID,
    scope_user: UUID | None,
    project_id: UUID | None,
    from_dt: datetime,
    to_dt: datetime,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = [
        AiUsageEvent.organization_id == organization_id,
        AiUsageEvent.occurred_at >= from_dt,
        AiUsageEvent.occurred_at <= to_dt,
    ]
    if scope_user is not None:
        filters.append(AiUsageEvent.user_id == scope_user)
    if project_id is not None:
        filters.append(AiUsageEvent.project_id == project_id)
    return filters


async def build_usage_summary(
    session: AsyncSession,
    *,
    organization_id: UUID,
    scope: str,
    current_user_id: UUID,
    from_dt: datetime,
    to_dt: datetime,
    project_id: UUID | None = None,
) -> AiUsageSummary:
    if from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=timezone.utc)
    if to_dt.tzinfo is None:
        to_dt = to_dt.replace(tzinfo=timezone.utc)

    scope_user = current_user_id if scope == "me" else None
    filters = _scope_filters(
        organization_id=organization_id,
        scope_user=scope_user,
        project_id=project_id,
        from_dt=from_dt,
        to_dt=to_dt,
    )
    where = and_(*filters)

    totals_row = (
        await session.execute(
            select(
                func.count(AiUsageEvent.id),
                func.coalesce(func.sum(AiUsageEvent.input_tokens), 0),
                func.coalesce(func.sum(AiUsageEvent.output_tokens), 0),
                func.coalesce(func.sum(AiUsageEvent.total_tokens), 0),
                func.count(func.distinct(AiUsageEvent.project_id)),
                func.count(func.distinct(AiUsageEvent.user_id)),
                func.count(func.distinct(AiUsageEvent.session_id)),
            ).where(where)
        )
    ).one()

    totals = AiUsageTotals(
        messages=int(totals_row[0] or 0),
        input_tokens=int(totals_row[1] or 0),
        output_tokens=int(totals_row[2] or 0),
        total_tokens=int(totals_row[3] or 0),
        projects=int(totals_row[4] or 0),
        users=int(totals_row[5] or 0),
        sessions=int(totals_row[6] or 0),
    )

    # Daily series — use date() for portability (SQLite + Postgres).
    day_col = func.date(AiUsageEvent.occurred_at)
    daily_stmt = (
        select(
            day_col.label("day"),
            func.coalesce(func.sum(AiUsageEvent.total_tokens), 0),
            func.count(AiUsageEvent.id),
        )
        .where(where)
        .group_by(day_col)
        .order_by(day_col.asc())
    )

    series_daily: list[AiUsageDailyPoint] = []
    for day, tokens, messages in (await session.execute(daily_stmt)).all():
        series_daily.append(
            AiUsageDailyPoint(
                date=str(day),
                tokens=int(tokens or 0),
                messages=int(messages or 0),
            )
        )

    model_stmt = (
        select(
            AiUsageEvent.provider,
            AiUsageEvent.model,
            func.coalesce(func.sum(AiUsageEvent.total_tokens), 0),
            func.count(AiUsageEvent.id),
        )
        .where(where)
        .group_by(AiUsageEvent.provider, AiUsageEvent.model)
        .order_by(func.coalesce(func.sum(AiUsageEvent.total_tokens), 0).desc())
    )

    by_model = [
        AiUsageByModel(
            provider=provider,
            model=model,
            tokens=int(tokens or 0),
            messages=int(messages or 0),
        )
        for provider, model, tokens, messages in (await session.execute(model_stmt)).all()
    ]

    project_stmt = (
        select(
            AiUsageEvent.project_id,
            Project.name,
            func.coalesce(func.sum(AiUsageEvent.total_tokens), 0),
            func.count(AiUsageEvent.id),
        )
        .join(Project, Project.id == AiUsageEvent.project_id)
        .where(where)
        .group_by(AiUsageEvent.project_id, Project.name)
        .order_by(func.coalesce(func.sum(AiUsageEvent.total_tokens), 0).desc())
    )

    by_project = [
        AiUsageByProject(
            project_id=pid,
            project_name=name or "Unknown",
            tokens=int(tokens or 0),
            messages=int(messages or 0),
        )
        for pid, name, tokens, messages in (await session.execute(project_stmt)).all()
    ]

    by_user: list[AiUsageByUser] = []
    if scope == "org":
        # Org scope ignores per-user filter from scope_user (already None).
        user_stmt = (
            select(
                AiUsageEvent.user_id,
                User.email,
                func.coalesce(func.sum(AiUsageEvent.total_tokens), 0),
                func.count(AiUsageEvent.id),
            )
            .join(User, User.id == AiUsageEvent.user_id)
            .where(where)
            .group_by(AiUsageEvent.user_id, User.email)
            .order_by(func.coalesce(func.sum(AiUsageEvent.total_tokens), 0).desc())
        )
        by_user = [
            AiUsageByUser(
                user_id=uid,
                email=email or "",
                tokens=int(tokens or 0),
                messages=int(messages or 0),
            )
            for uid, email, tokens, messages in (await session.execute(user_stmt)).all()
        ]

    return AiUsageSummary.model_validate(
        {
            "scope": scope,
            "from": from_dt,
            "to": to_dt,
            "totals": totals,
            "series_daily": series_daily,
            "by_model": by_model,
            "by_project": by_project,
            "by_user": by_user,
        }
    )
