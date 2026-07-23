"""Blank workflow create + data tables API + persistence on execute."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _project(client: AsyncClient, headers: dict[str, str], slug: str) -> str:
    org = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "Lib", "slug": f"org-{slug}"},
    )
    assert org.status_code == 201, org.text
    proj = await client.post(
        f"/api/v1/orgs/{org.json()['id']}/projects",
        headers=headers,
        json={"name": "Lib", "slug": slug},
    )
    assert proj.status_code == 201, proj.text
    return proj.json()["id"]


@pytest.mark.asyncio
async def test_create_blank_workflow(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project_id = await _project(client, auth_headers, "lib-blank")
    created = await client.post(
        f"/api/v1/projects/{project_id}/workflows",
        headers=auth_headers,
        json={"name": "My first flow"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "My first flow"
    assert body["graph"]["report"]["node_count"] == 1
    types = [n["type"] for n in body["graph"]["nodes"]]
    assert "n8n-nodes-base.manualTrigger" in types

    listed = await client.get(
        f"/api/v1/projects/{project_id}/workflows",
        headers=auth_headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1


@pytest.mark.asyncio
async def test_data_tables_crud(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project_id = await _project(client, auth_headers, "lib-tables")
    empty = await client.get(
        f"/api/v1/projects/{project_id}/workflow-data-tables",
        headers=auth_headers,
    )
    assert empty.status_code == 200
    assert empty.json() == []

    created = await client.post(
        f"/api/v1/projects/{project_id}/workflow-data-tables",
        headers=auth_headers,
        json={"name": "research", "columns": [{"id": "output", "type": "string"}]},
    )
    assert created.status_code == 201, created.text
    tid = created.json()["id"]
    assert created.json()["row_count"] == 0

    row = await client.post(
        f"/api/v1/projects/{project_id}/workflow-data-tables/{tid}/rows",
        headers=auth_headers,
        json={"data": {"output": "hello"}},
    )
    assert row.status_code == 201, row.text
    assert row.json()["row_count"] == 1
    assert row.json()["rows"][0]["output"] == "hello"

    got = await client.get(
        f"/api/v1/projects/{project_id}/workflow-data-tables/{tid}",
        headers=auth_headers,
    )
    assert got.status_code == 200
    assert got.json()["name"] == "research"

    listed = await client.get(
        f"/api/v1/projects/{project_id}/workflow-data-tables",
        headers=auth_headers,
    )
    assert len(listed.json()) == 1
    assert listed.json()[0]["row_count"] == 1

    deleted = await client.delete(
        f"/api/v1/projects/{project_id}/workflow-data-tables/{tid}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_execute_persists_data_table(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Mini workflow: trigger → create table → set → insert row."""
    project_id = await _project(client, auth_headers, "lib-persist")
    doc = {
        "name": "persist-table",
        "nodes": [
            {
                "id": "t1",
                "name": "Start",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [0, 0],
                "parameters": {},
            },
            {
                "id": "c1",
                "name": "Create",
                "type": "n8n-nodes-base.dataTable",
                "typeVersion": 1.1,
                "position": [200, 0],
                "parameters": {
                    "resource": "table",
                    "operation": "create",
                    "tableName": "persist_demo",
                    "columns": {"column": [{"name": "msg"}]},
                },
            },
            {
                "id": "s1",
                "name": "Set",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3,
                "position": [400, 0],
                "parameters": {
                    "assignments": {
                        "assignments": [{"name": "msg", "value": "from-run", "type": "string"}]
                    },
                    "includeOtherFields": True,
                },
            },
            {
                "id": "i1",
                "name": "Insert",
                "type": "n8n-nodes-base.dataTable",
                "typeVersion": 1.1,
                "position": [600, 0],
                "parameters": {
                    "dataTableId": {"__rl": True, "value": "persist_demo", "mode": "name"},
                    "columns": {
                        "mappingMode": "defineBelow",
                        "value": {"msg": "={{ $json.msg }}"},
                    },
                },
            },
        ],
        "connections": {
            "Start": {"main": [[{"node": "Create", "type": "main", "index": 0}]]},
            "Create": {"main": [[{"node": "Set", "type": "main", "index": 0}]]},
            "Set": {"main": [[{"node": "Insert", "type": "main", "index": 0}]]},
        },
    }
    imp = await client.post(
        f"/api/v1/projects/{project_id}/workflows/import",
        headers=auth_headers,
        json=doc,
    )
    assert imp.status_code == 201, imp.text
    wf_id = imp.json()["id"]

    exe = await client.post(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}/execute",
        headers=auth_headers,
        json={"trigger": "manual", "dry_run": True, "background": False},
    )
    assert exe.status_code == 201, exe.text
    assert exe.json()["status"] == "success", exe.json().get("error_message")

    tables = await client.get(
        f"/api/v1/projects/{project_id}/workflow-data-tables",
        headers=auth_headers,
    )
    assert tables.status_code == 200
    assert any(t["name"] == "persist_demo" for t in tables.json())
    tid = next(t["id"] for t in tables.json() if t["name"] == "persist_demo")
    detail = await client.get(
        f"/api/v1/projects/{project_id}/workflow-data-tables/{tid}",
        headers=auth_headers,
    )
    assert detail.json()["row_count"] >= 1
    assert any(r.get("msg") == "from-run" for r in detail.json()["rows"])
