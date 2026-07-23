"""Project-scoped n8n-compatible workflow CRUD, import, and execute."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.principal import Principal, get_principal, get_project_for_principal
from app.db.session import get_async_session, get_session_factory
from app.models.project import Project
from app.models.workflow import (
    Workflow,
    WorkflowCredential,
    WorkflowDataTable,
    WorkflowDataTableRow,
    WorkflowRun,
)
from app.schemas.workflow import (
    WorkflowCreateBody,
    WorkflowCredentialCreate,
    WorkflowCredentialRead,
    WorkflowDataTableCreate,
    WorkflowDataTableRead,
    WorkflowDataTableRowCreate,
    WorkflowDataTableSummary,
    WorkflowExecuteBody,
    WorkflowGraph,
    WorkflowRead,
    WorkflowRunRead,
    WorkflowSummary,
    WorkflowUpdate,
    WorkflowValidateResponse,
)
from app.services.workflows.credentials_store import decrypt_payload, encrypt_payload
from app.services.workflows.data_tables_store import (
    blank_workflow_document,
    flush_project_tables,
    load_project_tables,
)
from app.services.workflows.engine import StepLog, WorkflowEngine
from app.services.workflows.import_n8n import import_n8n_document
from app.services.workflows.preflight import preflight_workflow

logger = logging.getLogger(__name__)

router = APIRouter(tags=["workflows"])

# In-process cancel flags for active runs
_run_cancel: dict[str, bool] = {}


def _graph_from_document(document: dict[str, Any]) -> WorkflowGraph:
    derived = import_n8n_document(document)
    return WorkflowGraph.model_validate(derived.to_dict())


def _to_read(wf: Workflow) -> WorkflowRead:
    doc = wf.n8n_document if isinstance(wf.n8n_document, dict) else {}
    graph = _graph_from_document(doc)
    return WorkflowRead(
        id=wf.id,
        project_id=wf.project_id,
        name=wf.name,
        active=wf.active,
        trigger_summary=wf.trigger_summary,
        settings=wf.settings,
        credential_bindings=wf.credential_bindings,
        import_report=wf.import_report,
        n8n_document=doc,
        graph=graph,
        created_by=wf.created_by,
        created_at=wf.created_at,
        updated_at=wf.updated_at,
    )


def _to_summary(wf: Workflow) -> WorkflowSummary:
    report = wf.import_report if isinstance(wf.import_report, dict) else {}
    return WorkflowSummary(
        id=wf.id,
        project_id=wf.project_id,
        name=wf.name,
        active=wf.active,
        trigger_summary=wf.trigger_summary,
        created_by=wf.created_by,
        created_at=wf.created_at,
        updated_at=wf.updated_at,
        node_count=report.get("node_count"),
        unsupported_count=len(report.get("unsupported_types") or []),
        credential_requirements_count=len(report.get("credential_requirements") or []),
    )


async def _get_workflow(
    session: AsyncSession,
    project_id: UUID,
    workflow_id: UUID,
) -> Workflow:
    result = await session.execute(
        select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.project_id == project_id,
        )
    )
    wf = result.scalar_one_or_none()
    if wf is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return wf


def _extract_document(body: dict[str, Any]) -> dict[str, Any]:
    """Accept either {document: {...}} or a raw n8n export at the top level."""
    if "document" in body and isinstance(body["document"], dict):
        return body["document"]
    # Raw n8n export has nodes at top level
    if "nodes" in body:
        # Strip Everflow-only keys if client mixed them
        doc = {k: v for k, v in body.items() if k not in ("credential_bindings",)}
        # If name/active were Everflow overrides on a wrapper without document,
        # keep them in the n8n doc (n8n also has name/active).
        return doc
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Body must be an n8n export (with 'nodes') or {document: <n8n export>}",
    )


@router.get(
    "/projects/{project_id}/workflows",
    response_model=list[WorkflowSummary],
)
async def list_workflows(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[WorkflowSummary]:
    principal.require_scope("workflows:read")
    result = await session.execute(
        select(Workflow)
        .where(Workflow.project_id == project.id)
        .order_by(Workflow.updated_at.desc())
    )
    return [_to_summary(w) for w in result.scalars().all()]


@router.post(
    "/projects/{project_id}/workflows",
    response_model=WorkflowRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow(
    body: WorkflowCreateBody,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkflowRead:
    """Create a blank workflow (manual trigger) or from an optional document."""
    principal.require_scope("workflows:rw")
    name = body.name.strip() or "Untitled workflow"
    if body.document is not None:
        try:
            derived = import_n8n_document(body.document)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        stored_doc = dict(body.document)
        stored_doc["name"] = name
        stored_doc["active"] = body.active
        settings = derived.settings
        trigger_summary = derived.report.trigger_summary
        import_report = derived.report.to_dict()
    else:
        stored_doc = blank_workflow_document(name)
        stored_doc["active"] = body.active
        derived = import_n8n_document(stored_doc)
        settings = derived.settings
        trigger_summary = derived.report.trigger_summary
        import_report = derived.report.to_dict()

    wf = Workflow(
        project_id=project.id,
        name=name,
        active=body.active,
        n8n_document=stored_doc,
        settings=settings,
        trigger_summary=trigger_summary,
        credential_bindings={},
        import_report=import_report,
        created_by=principal.user.id,
    )
    session.add(wf)
    await session.commit()
    await session.refresh(wf)
    return _to_read(wf)


@router.post(
    "/projects/{project_id}/workflows/import",
    response_model=WorkflowRead,
    status_code=status.HTTP_201_CREATED,
)
async def import_workflow(
    body: dict[str, Any],
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkflowRead:
    principal.require_scope("workflows:rw")
    document = _extract_document(body)
    try:
        derived = import_n8n_document(document)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    name_override = body.get("name")
    active_override = body.get("active")
    bindings = body.get("credential_bindings")
    if not isinstance(bindings, dict):
        bindings = {}

    name = str(name_override).strip() if name_override else derived.name
    active = bool(active_override) if active_override is not None else derived.active

    # Ensure stored document has consistent name
    stored_doc = dict(document)
    stored_doc["name"] = name
    stored_doc["active"] = active

    wf = Workflow(
        project_id=project.id,
        name=name,
        active=active,
        n8n_document=stored_doc,
        settings=derived.settings,
        trigger_summary=derived.report.trigger_summary,
        credential_bindings=bindings,
        import_report=derived.report.to_dict(),
        created_by=principal.user.id,
    )
    session.add(wf)
    await session.commit()
    await session.refresh(wf)
    return _to_read(wf)


@router.get(
    "/projects/{project_id}/workflows/{workflow_id}",
    response_model=WorkflowRead,
)
async def get_workflow(
    workflow_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkflowRead:
    principal.require_scope("workflows:read")
    wf = await _get_workflow(session, project.id, workflow_id)
    return _to_read(wf)


@router.patch(
    "/projects/{project_id}/workflows/{workflow_id}",
    response_model=WorkflowRead,
)
async def update_workflow(
    workflow_id: UUID,
    body: WorkflowUpdate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkflowRead:
    principal.require_scope("workflows:rw")
    wf = await _get_workflow(session, project.id, workflow_id)

    if body.n8n_document is not None:
        try:
            derived = import_n8n_document(body.n8n_document)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        wf.n8n_document = body.n8n_document
        wf.settings = derived.settings
        wf.trigger_summary = derived.report.trigger_summary
        wf.import_report = derived.report.to_dict()
        if body.name is None:
            wf.name = derived.name

    if body.name is not None:
        wf.name = body.name.strip()
        if isinstance(wf.n8n_document, dict):
            wf.n8n_document = {**wf.n8n_document, "name": wf.name}

    if body.active is not None:
        wf.active = body.active
        if isinstance(wf.n8n_document, dict):
            wf.n8n_document = {**wf.n8n_document, "active": wf.active}

    if body.credential_bindings is not None:
        wf.credential_bindings = body.credential_bindings

    await session.commit()
    await session.refresh(wf)
    return _to_read(wf)


@router.delete(
    "/projects/{project_id}/workflows/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_workflow(
    workflow_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("workflows:rw")
    wf = await _get_workflow(session, project.id, workflow_id)
    await session.delete(wf)
    await session.commit()


@router.get(
    "/projects/{project_id}/workflows/{workflow_id}/export",
    response_model=dict[str, Any],
)
async def export_workflow(
    workflow_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """Return the stored n8n document (round-trip export)."""
    principal.require_scope("workflows:read")
    wf = await _get_workflow(session, project.id, workflow_id)
    doc = wf.n8n_document if isinstance(wf.n8n_document, dict) else {}
    return doc


@router.get(
    "/projects/{project_id}/workflows/{workflow_id}/runs",
    response_model=list[WorkflowRunRead],
)
async def list_runs(
    workflow_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[WorkflowRun]:
    principal.require_scope("workflows:read")
    await _get_workflow(session, project.id, workflow_id)
    result = await session.execute(
        select(WorkflowRun)
        .where(
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.project_id == project.id,
        )
        .order_by(WorkflowRun.started_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


@router.get(
    "/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}",
    response_model=WorkflowRunRead,
)
async def get_run(
    workflow_id: UUID,
    run_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkflowRun:
    principal.require_scope("workflows:read")
    await _get_workflow(session, project.id, workflow_id)
    result = await session.execute(
        select(WorkflowRun).where(
            WorkflowRun.id == run_id,
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.project_id == project.id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


async def _load_project_credentials(
    session: AsyncSession,
    project_id: UUID,
) -> dict[str, dict[str, Any]]:
    """Map credential keys for the engine."""
    result = await session.execute(
        select(WorkflowCredential).where(WorkflowCredential.project_id == project_id)
    )
    out: dict[str, dict[str, Any]] = {}
    for row in result.scalars().all():
        try:
            payload = decrypt_payload(row.secret_ciphertext, row.secret_nonce)
        except Exception:
            continue
        out[row.credential_type] = payload
        out[f"{row.credential_type}:{row.name}"] = payload
        out[row.name] = payload
        out[str(row.id)] = payload
    return out


def _has_smtp(stored: dict[str, dict[str, Any]]) -> bool:
    return any(k == "smtp" or str(k).startswith("smtp:") for k in stored)


def _finalize_log(result: Any) -> list[Any]:
    return [
        *(result.to_dict().get("steps") or []),
        {
            "summary": True,
            "status": result.status,
            "final_items": result.final_items[:5],
            "data_tables": result.to_dict().get("data_tables"),
            "sent_emails": [
                {
                    "to": e.get("to"),
                    "subject": e.get("subject"),
                    "html_chars": len(str(e.get("html") or "")),
                    "text_chars": len(str(e.get("text") or "")),
                }
                for e in result.sent_emails
            ],
        },
    ]


async def _execute_engine(
    *,
    run_id: UUID,
    project_id: UUID,
    doc: dict[str, Any],
    stored: dict[str, dict[str, Any]],
    bindings: dict[str, str],
    mocks: dict[str, Any],
    trigger: str,
    pin_data: dict[str, list[dict[str, Any]]] | None,
) -> None:
    """Run engine and persist steps + data tables (used sync or background)."""
    rid = str(run_id)
    _run_cancel[rid] = False
    factory = get_session_factory()

    async def on_step(step: StepLog) -> None:
        async with factory() as s:
            row = await s.get(WorkflowRun, run_id)
            if row is None:
                return
            log = list(row.log or [])
            log.append(step.to_dict())
            row.log = log
            await s.commit()

    # Hydrate data tables from DB
    async with factory() as s:
        data_tables = await load_project_tables(s, project_id)

    engine = WorkflowEngine(
        doc,
        credentials=stored,
        credential_bindings=bindings,
        mocks=mocks,
        data_tables=data_tables,
        on_step=on_step,
        cancel_check=lambda: bool(_run_cancel.get(rid)),
    )
    try:
        result = await engine.run(trigger=trigger, pin_data=pin_data)
        status_final = result.status
        if result.error_message == "cancelled":
            status_final = "cancelled"
        async with factory() as s:
            row = await s.get(WorkflowRun, run_id)
            if row is None:
                return
            row.status = status_final
            row.error_message = result.error_message
            row.log = _finalize_log(result)
            row.finished_at = datetime.now(timezone.utc)
            await s.commit()
            # Persist data tables as left by the engine
            await flush_project_tables(s, project_id, result.data_tables)
    except Exception as exc:
        logger.exception("Workflow execute failed run=%s", run_id)
        async with factory() as s:
            row = await s.get(WorkflowRun, run_id)
            if row is None:
                return
            row.status = "error"
            row.error_message = str(exc)
            row.finished_at = datetime.now(timezone.utc)
            await s.commit()
            # Still try to flush partial tables
            try:
                await flush_project_tables(s, project_id, engine.data_tables)
            except Exception:
                logger.exception("Failed to flush data tables after error")
    finally:
        _run_cancel.pop(rid, None)


@router.post(
    "/projects/{project_id}/workflows/{workflow_id}/validate-run",
    response_model=WorkflowValidateResponse,
)
async def validate_run(
    workflow_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkflowValidateResponse:
    principal.require_scope("workflows:read")
    wf = await _get_workflow(session, project.id, workflow_id)
    doc = wf.n8n_document if isinstance(wf.n8n_document, dict) else {}
    stored = await _load_project_credentials(session, project.id)
    report = preflight_workflow(
        doc,
        credential_bindings=wf.credential_bindings if isinstance(wf.credential_bindings, dict) else {},
        available_credential_keys=set(stored.keys()),
        available_by_type={k for k in stored if ":" not in k and len(k) < 64},
    )
    return WorkflowValidateResponse.model_validate(report)


@router.post(
    "/projects/{project_id}/workflows/{workflow_id}/execute",
    response_model=WorkflowRunRead,
    status_code=status.HTTP_201_CREATED,
)
async def execute_workflow(
    workflow_id: UUID,
    body: WorkflowExecuteBody | None = None,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkflowRun:
    # Allow execute with rw scope as well (JWT always ok; sandbox needs either)
    if principal.via != "jwt":
        try:
            principal.require_scope("workflows:execute")
        except HTTPException:
            principal.require_scope("workflows:rw")
    body = body or WorkflowExecuteBody()
    wf = await _get_workflow(session, project.id, workflow_id)
    doc = wf.n8n_document if isinstance(wf.n8n_document, dict) else {}

    stored = await _load_project_credentials(session, project.id)
    if body.credentials:
        for k, v in body.credentials.items():
            if isinstance(v, dict):
                stored[k] = v

    bindings_raw = wf.credential_bindings if isinstance(wf.credential_bindings, dict) else {}
    bindings = {str(k): str(v) for k, v in bindings_raw.items()}
    mocks = dict(body.mocks or {})

    # Dry-run: capture email + allow missing live services
    # Live: only capture when SMTP not configured
    if body.dry_run:
        mocks.setdefault("capture_email", True)
        if "ftp_files" not in mocks and "agent_output" not in mocks:
            # soft offline agent if no key
            if not any(k == "openAiApi" or str(k).startswith("openAiApi") for k in stored):
                mocks.setdefault(
                    "agent_output",
                    "# Dry-run report\n\nExecuted without live LLM (no openAiApi credential).\n",
                )
    else:
        if "capture_email" not in mocks and not _has_smtp(stored):
            mocks["capture_email"] = True

    run = WorkflowRun(
        workflow_id=wf.id,
        project_id=project.id,
        status="running",
        trigger_type=body.trigger,
        log=[],
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)

    if body.background:
        asyncio.create_task(
            _execute_engine(
                run_id=run.id,
                project_id=project.id,
                doc=doc,
                stored=stored,
                bindings=bindings,
                mocks=mocks,
                trigger=body.trigger,
                pin_data=body.pin_data,
            )
        )
        return run

    await _execute_engine(
        run_id=run.id,
        project_id=project.id,
        doc=doc,
        stored=stored,
        bindings=bindings,
        mocks=mocks,
        trigger=body.trigger,
        pin_data=body.pin_data,
    )
    await session.refresh(run)
    # re-load from DB for updated status
    result = await session.execute(select(WorkflowRun).where(WorkflowRun.id == run.id))
    fresh = result.scalar_one()
    return fresh


@router.post(
    "/projects/{project_id}/workflows/{workflow_id}/runs/{run_id}/cancel",
    response_model=WorkflowRunRead,
)
async def cancel_run(
    workflow_id: UUID,
    run_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkflowRun:
    if principal.via != "jwt":
        try:
            principal.require_scope("workflows:execute")
        except HTTPException:
            principal.require_scope("workflows:rw")
    await _get_workflow(session, project.id, workflow_id)
    result = await session.execute(
        select(WorkflowRun).where(
            WorkflowRun.id == run_id,
            WorkflowRun.workflow_id == workflow_id,
            WorkflowRun.project_id == project.id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    _run_cancel[str(run_id)] = True
    if run.status == "running":
        # mark intent; engine will finalize
        run.error_message = run.error_message or "cancel requested"
        await session.commit()
        await session.refresh(run)
    return run


# ── Credentials ──────────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/workflow-credentials",
    response_model=list[WorkflowCredentialRead],
)
async def list_credentials(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[WorkflowCredential]:
    principal.require_scope("workflows:read")
    result = await session.execute(
        select(WorkflowCredential)
        .where(WorkflowCredential.project_id == project.id)
        .order_by(WorkflowCredential.updated_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/projects/{project_id}/workflow-credentials",
    response_model=WorkflowCredentialRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_credential(
    body: WorkflowCredentialCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkflowCredential:
    principal.require_scope("workflows:rw")
    ct, nonce = encrypt_payload(body.payload)
    row = WorkflowCredential(
        project_id=project.id,
        credential_type=body.credential_type.strip(),
        name=body.name.strip(),
        secret_ciphertext=ct,
        secret_nonce=nonce,
        created_by=principal.user.id,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete(
    "/projects/{project_id}/workflow-credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_credential(
    credential_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("workflows:rw")
    result = await session.execute(
        select(WorkflowCredential).where(
            WorkflowCredential.id == credential_id,
            WorkflowCredential.project_id == project.id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Credential not found")
    await session.delete(row)
    await session.commit()


# ── Data tables ──────────────────────────────────────────────────────


async def _table_for_project(
    session: AsyncSession,
    project_id: UUID,
    table_id: UUID,
) -> WorkflowDataTable:
    result = await session.execute(
        select(WorkflowDataTable)
        .where(
            WorkflowDataTable.id == table_id,
            WorkflowDataTable.project_id == project_id,
        )
        .options(selectinload(WorkflowDataTable.rows))
    )
    table = result.scalar_one_or_none()
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data table not found")
    return table


@router.get(
    "/projects/{project_id}/workflow-data-tables",
    response_model=list[WorkflowDataTableSummary],
)
async def list_data_tables(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[WorkflowDataTableSummary]:
    principal.require_scope("workflows:read")
    result = await session.execute(
        select(WorkflowDataTable)
        .where(WorkflowDataTable.project_id == project.id)
        .options(selectinload(WorkflowDataTable.rows))
        .order_by(WorkflowDataTable.updated_at.desc())
    )
    out: list[WorkflowDataTableSummary] = []
    for t in result.scalars().all():
        out.append(
            WorkflowDataTableSummary(
                id=t.id,
                project_id=t.project_id,
                name=t.name,
                columns=t.schema_json,
                row_count=len(t.rows or []),
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
        )
    return out


@router.post(
    "/projects/{project_id}/workflow-data-tables",
    response_model=WorkflowDataTableRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_data_table(
    body: WorkflowDataTableCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkflowDataTableRead:
    principal.require_scope("workflows:rw")
    name = body.name.strip()
    # unique-ish by name per project
    existing = await session.execute(
        select(WorkflowDataTable).where(
            WorkflowDataTable.project_id == project.id,
            WorkflowDataTable.name == name,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Data table '{name}' already exists",
        )
    table = WorkflowDataTable(
        project_id=project.id,
        name=name,
        schema_json=body.columns or [],
    )
    session.add(table)
    await session.commit()
    await session.refresh(table)
    return WorkflowDataTableRead(
        id=table.id,
        project_id=table.project_id,
        name=table.name,
        columns=table.schema_json,
        rows=[],
        row_count=0,
        created_at=table.created_at,
        updated_at=table.updated_at,
    )


@router.get(
    "/projects/{project_id}/workflow-data-tables/{table_id}",
    response_model=WorkflowDataTableRead,
)
async def get_data_table(
    table_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
    limit: int = 100,
    offset: int = 0,
) -> WorkflowDataTableRead:
    principal.require_scope("workflows:read")
    table = await _table_for_project(session, project.id, table_id)
    rows_sorted = sorted(table.rows or [], key=lambda r: r.row_index)
    slice_rows = rows_sorted[offset : offset + max(1, min(limit, 500))]
    return WorkflowDataTableRead(
        id=table.id,
        project_id=table.project_id,
        name=table.name,
        columns=table.schema_json,
        rows=[dict(r.data or {}) for r in slice_rows],
        row_count=len(rows_sorted),
        created_at=table.created_at,
        updated_at=table.updated_at,
    )


@router.delete(
    "/projects/{project_id}/workflow-data-tables/{table_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_data_table(
    table_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("workflows:rw")
    table = await _table_for_project(session, project.id, table_id)
    await session.delete(table)
    await session.commit()


@router.post(
    "/projects/{project_id}/workflow-data-tables/{table_id}/rows",
    response_model=WorkflowDataTableRead,
    status_code=status.HTTP_201_CREATED,
)
async def insert_data_table_row(
    table_id: UUID,
    body: WorkflowDataTableRowCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkflowDataTableRead:
    principal.require_scope("workflows:rw")
    table = await _table_for_project(session, project.id, table_id)
    count_result = await session.execute(
        select(WorkflowDataTableRow).where(WorkflowDataTableRow.table_id == table.id)
    )
    existing_rows = list(count_result.scalars().all())
    next_idx = max((r.row_index for r in existing_rows), default=-1) + 1
    session.add(
        WorkflowDataTableRow(
            table_id=table.id,
            data=dict(body.data),
            row_index=next_idx,
        )
    )
    await session.commit()
    # Re-query rows explicitly (avoid stale relationship cache)
    rows_result = await session.execute(
        select(WorkflowDataTableRow)
        .where(WorkflowDataTableRow.table_id == table_id)
        .order_by(WorkflowDataTableRow.row_index)
    )
    rows_sorted = list(rows_result.scalars().all())
    table = await session.get(WorkflowDataTable, table_id)
    assert table is not None
    return WorkflowDataTableRead(
        id=table.id,
        project_id=table.project_id,
        name=table.name,
        columns=table.schema_json,
        rows=[dict(r.data or {}) for r in rows_sorted],
        row_count=len(rows_sorted),
        created_at=table.created_at,
        updated_at=table.updated_at,
    )

