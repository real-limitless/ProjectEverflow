"""In-process workflow schedule arming (v1 — single API process)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

_task: asyncio.Task[None] | None = None
_stop = asyncio.Event()


def parse_schedule_hours(document: dict[str, Any]) -> list[int]:
    """Extract triggerAtHour values from scheduleTrigger nodes (0-23)."""
    hours: list[int] = []
    for n in document.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        if "scheduleTrigger" not in str(n.get("type") or ""):
            continue
        params = n.get("parameters") or {}
        rule = params.get("rule") if isinstance(params, dict) else None
        if not isinstance(rule, dict):
            continue
        for interval in rule.get("interval") or []:
            if not isinstance(interval, dict):
                continue
            if "triggerAtHour" in interval:
                try:
                    hours.append(int(interval["triggerAtHour"]) % 24)
                except (TypeError, ValueError):
                    pass
    return sorted(set(hours)) if hours else []


def next_fire_utc(hours: list[int], now: datetime | None = None) -> datetime | None:
    if not hours:
        return None
    now = now or datetime.now(timezone.utc)
    # candidate today and tomorrow at each hour
    candidates: list[datetime] = []
    for d in (0, 1):
        day = (now + timedelta(days=d)).date()
        for h in hours:
            dt = datetime(day.year, day.month, day.day, h, 0, 0, tzinfo=timezone.utc)
            if dt > now:
                candidates.append(dt)
    return min(candidates) if candidates else None


async def _tick_once() -> None:
    """Load active workflows and fire due schedule triggers."""
    from sqlalchemy import select

    from app.db.session import get_session_factory
    from app.models.workflow import Workflow, WorkflowRun
    from app.services.workflows.credentials_store import decrypt_payload
    from app.services.workflows.engine import WorkflowEngine
    from app.models.workflow import WorkflowCredential

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Workflow).where(Workflow.active.is_(True)))
        workflows = list(result.scalars().all())

    now = datetime.now(timezone.utc)
    for wf in workflows:
        doc = wf.n8n_document if isinstance(wf.n8n_document, dict) else {}
        hours = parse_schedule_hours(doc)
        if not hours:
            continue
        # Fire if current UTC hour matches and we haven't fired this hour
        if now.hour not in hours:
            continue
        async with factory() as session:
            # skip if already ran this hour for schedule
            since = now.replace(minute=0, second=0, microsecond=0)
            existing = await session.execute(
                select(WorkflowRun).where(
                    WorkflowRun.workflow_id == wf.id,
                    WorkflowRun.trigger_type == "schedule",
                    WorkflowRun.started_at >= since,
                )
            )
            if existing.scalars().first() is not None:
                continue

            cred_rows = await session.execute(
                select(WorkflowCredential).where(WorkflowCredential.project_id == wf.project_id)
            )
            stored: dict[str, dict[str, Any]] = {}
            for row in cred_rows.scalars().all():
                try:
                    payload = decrypt_payload(row.secret_ciphertext, row.secret_nonce)
                except Exception:
                    continue
                stored[row.credential_type] = payload
                stored[f"{row.credential_type}:{row.name}"] = payload
                stored[row.name] = payload
                stored[str(row.id)] = payload

            bindings = wf.credential_bindings if isinstance(wf.credential_bindings, dict) else {}
            run = WorkflowRun(
                workflow_id=wf.id,
                project_id=wf.project_id,
                status="running",
                trigger_type="schedule",
                log=[],
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            run_id = run.id
            project_id = wf.project_id
            doc_copy = dict(doc)
            bind_copy = {str(k): str(v) for k, v in bindings.items()}

        try:
            engine = WorkflowEngine(
                doc_copy,
                credentials=stored,
                credential_bindings=bind_copy,
                mocks={"capture_email": "smtp" not in stored and "smtp:" not in str(stored.keys())},
            )
            # simpler: always capture if no smtp type
            if not any(k == "smtp" or k.startswith("smtp:") for k in stored):
                engine.mocks["capture_email"] = True
            result = await engine.run(trigger="schedule")
            async with factory() as session:
                row = await session.get(WorkflowRun, run_id)
                if row is None:
                    continue
                row.status = result.status if result.status != "error" or result.error_message != "cancelled" else result.status
                if result.error_message == "cancelled":
                    row.status = "cancelled"
                row.error_message = result.error_message
                row.log = [
                    *(result.to_dict().get("steps") or []),
                    {"summary": True, "status": result.status, "scheduled": True},
                ]
                row.finished_at = datetime.now(timezone.utc)
                await session.commit()
            logger.info("Scheduled run %s for workflow %s → %s", run_id, wf.id, result.status)
        except Exception:
            logger.exception("Scheduled run failed for workflow %s", wf.id)
            async with factory() as session:
                row = await session.get(WorkflowRun, run_id)
                if row:
                    row.status = "error"
                    row.error_message = "scheduler exception"
                    row.finished_at = datetime.now(timezone.utc)
                    await session.commit()


async def _loop(interval_s: float = 60.0) -> None:
    logger.info("Workflow scheduler started (interval=%ss)", interval_s)
    while not _stop.is_set():
        try:
            await _tick_once()
        except Exception:
            logger.exception("Scheduler tick failed")
        try:
            await asyncio.wait_for(_stop.wait(), timeout=interval_s)
        except asyncio.TimeoutError:
            continue
    logger.info("Workflow scheduler stopped")


def start_scheduler(*, enabled: bool = True, interval_s: float = 60.0) -> None:
    global _task
    if not enabled:
        logger.info("Workflow scheduler disabled")
        return
    if _task is not None and not _task.done():
        return
    _stop.clear()
    _task = asyncio.create_task(_loop(interval_s), name="workflow-scheduler")


async def stop_scheduler() -> None:
    global _task
    _stop.set()
    if _task is not None:
        try:
            await asyncio.wait_for(_task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _task.cancel()
        _task = None


async def force_tick_for_tests() -> None:
    """Test helper: run one scheduler pass."""
    await _tick_once()
