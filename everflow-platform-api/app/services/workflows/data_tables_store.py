"""Persist n8n-style workflow data tables for a project."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.workflow import WorkflowDataTable, WorkflowDataTableRow


async def load_project_tables(
    session: AsyncSession,
    project_id: UUID,
) -> dict[str, dict[str, Any]]:
    """Return name -> {schema, rows} for engine hydrate."""
    result = await session.execute(
        select(WorkflowDataTable)
        .where(WorkflowDataTable.project_id == project_id)
        .options(selectinload(WorkflowDataTable.rows))
    )
    out: dict[str, dict[str, Any]] = {}
    for table in result.scalars().all():
        rows_sorted = sorted(table.rows or [], key=lambda r: r.row_index)
        out[table.name] = {
            "schema": list(table.schema_json or []),
            "rows": [dict(r.data or {}) for r in rows_sorted],
        }
    return out


async def flush_project_tables(
    session: AsyncSession,
    project_id: UUID,
    store: dict[str, dict[str, Any]],
) -> None:
    """Replace project tables to match engine store (names present only).

    Tables deleted during the run (popped from store) are removed from DB.
    """
    result = await session.execute(
        select(WorkflowDataTable).where(WorkflowDataTable.project_id == project_id)
    )
    existing = {t.name: t for t in result.scalars().all()}

    # Delete tables no longer in store
    for name, table in list(existing.items()):
        if name not in store:
            await session.delete(table)

    for name, payload in store.items():
        schema = payload.get("schema") if isinstance(payload.get("schema"), list) else []
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        table = existing.get(name)
        if table is None:
            table = WorkflowDataTable(
                project_id=project_id,
                name=name,
                schema_json=schema,
            )
            session.add(table)
            await session.flush()
        else:
            table.schema_json = schema
            # clear rows
            await session.execute(
                delete(WorkflowDataTableRow).where(WorkflowDataTableRow.table_id == table.id)
            )

        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            session.add(
                WorkflowDataTableRow(
                    id=uuid4(),
                    table_id=table.id,
                    data=dict(row),
                    row_index=i,
                )
            )

    await session.commit()


def blank_workflow_document(name: str = "Untitled workflow") -> dict[str, Any]:
    """Minimal n8n document with a manual trigger."""
    node_id = str(uuid4())
    return {
        "name": name,
        "active": False,
        "nodes": [
            {
                "id": node_id,
                "name": "Start",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [240, 300],
                "parameters": {},
            }
        ],
        "connections": {},
        "settings": {"executionOrder": "v1"},
        "pinData": {},
        "meta": {"everflowBlank": True},
    }
