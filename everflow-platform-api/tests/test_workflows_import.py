"""n8n workflow import parity and API lifecycle tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.services.workflows.import_n8n import import_n8n_document
from app.services.workflows.registry import SUPPORTED_NODE_TYPES

FIXTURE = Path(__file__).parent / "fixtures" / "workflows" / "stock_agent_emailer.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


async def _create_org_and_project(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    org_slug: str = "wf-org",
    project_slug: str = "wf-app",
) -> str:
    org = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "Workflow Org", "slug": org_slug},
    )
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]
    proj = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=headers,
        json={"name": "Workflow App", "slug": project_slug, "description": "n8n"},
    )
    assert proj.status_code == 201, proj.text
    return proj.json()["id"]


def test_stock_agent_import_parity() -> None:
    doc = _load_fixture()
    derived = import_n8n_document(doc)

    assert derived.name == "Stock Agent Emailer"
    assert derived.report.node_count == 32
    assert len(derived.nodes) == 32

    # All fixture types are in the supported registry
    types = {n.type for n in derived.nodes}
    assert types <= set(SUPPORTED_NODE_TYPES.keys()), (
        f"Unsupported types in fixture: {types - set(SUPPORTED_NODE_TYPES.keys())}"
    )
    assert derived.report.unsupported_types == []

    # Connection parity: main + AI edges
    counts = derived.report.connection_type_counts
    assert counts.get("main") == 26
    assert counts.get("ai_languageModel") == 1
    assert counts.get("ai_tool") == 5
    assert derived.report.edge_count == 32  # 26 + 1 + 5

    # Multi-entry triggers
    assert derived.report.trigger_summary == "mixed"

    # Credential requirements present
    cred_types = {c["credential_type"] for c in derived.report.credential_requirements}
    assert "openAiApi" in cred_types
    assert "ftp" in cred_types
    assert "smtp" in cred_types
    assert "httpMultipleHeadersAuth" in cred_types
    assert "mcpClientApi" in cred_types

    # AI edges target the agent
    agent = next(n for n in derived.nodes if n.name == "Single Stock Researcher")
    ai_edges = [e for e in derived.edges if e.target == agent.id and e.connection_type != "main"]
    assert len(ai_edges) == 6  # 1 model + 5 tools
    assert {e.connection_type for e in ai_edges} == {"ai_languageModel", "ai_tool"}

    # splitInBatches multi-output handles
    loop = next(n for n in derived.nodes if n.name == "Loop Over Portfolio Files")
    loop_edges = [e for e in derived.edges if e.source == loop.id and e.connection_type == "main"]
    handles = {e.source_handle for e in loop_edges}
    assert any("done" in h or h.endswith(":0") or ":0" in h for h in handles)
    assert any("loop" in h or ":1" in h for h in handles)

    # Positions preserved
    assert any(n.position["x"] != 0 or n.position["y"] != 0 for n in derived.nodes)


def test_import_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        import_n8n_document([])  # type: ignore[arg-type]


def test_import_rejects_missing_nodes() -> None:
    with pytest.raises(ValueError, match="nodes"):
        import_n8n_document({"name": "x"})


@pytest.mark.asyncio
async def test_workflow_import_api(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project_id = await _create_org_and_project(client, auth_headers)
    doc = _load_fixture()

    empty = await client.get(
        f"/api/v1/projects/{project_id}/workflows",
        headers=auth_headers,
    )
    assert empty.status_code == 200
    assert empty.json() == []

    # Import raw n8n document at top level
    imp = await client.post(
        f"/api/v1/projects/{project_id}/workflows/import",
        headers=auth_headers,
        json=doc,
    )
    assert imp.status_code == 201, imp.text
    body = imp.json()
    assert body["name"] == "Stock Agent Emailer"
    assert body["trigger_summary"] == "mixed"
    assert body["graph"]["report"]["node_count"] == 32
    assert body["graph"]["report"]["edge_count"] == 32
    assert len(body["graph"]["nodes"]) == 32
    assert len(body["graph"]["edges"]) == 32
    assert body["import_report"]["unsupported_types"] == []
    wf_id = body["id"]

    listed = await client.get(
        f"/api/v1/projects/{project_id}/workflows",
        headers=auth_headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["node_count"] == 32

    got = await client.get(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}",
        headers=auth_headers,
    )
    assert got.status_code == 200
    assert got.json()["graph"]["nodes"][0]["type"]

    exported = await client.get(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}/export",
        headers=auth_headers,
    )
    assert exported.status_code == 200
    exp = exported.json()
    assert len(exp["nodes"]) == 32
    assert len(exp["connections"]) == len(doc["connections"])

    patched = await client.patch(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}",
        headers=auth_headers,
        json={"name": "Stock Research", "active": True},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Stock Research"
    assert patched.json()["active"] is True

    runs = await client.get(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}/runs",
        headers=auth_headers,
    )
    assert runs.status_code == 200
    assert runs.json() == []

    deleted = await client.delete(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204

    gone = await client.get(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}",
        headers=auth_headers,
    )
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_workflow_import_wrapped_document(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    project_id = await _create_org_and_project(
        client, auth_headers, org_slug="wf-org-2", project_slug="wf-app-2"
    )
    doc = _load_fixture()
    imp = await client.post(
        f"/api/v1/projects/{project_id}/workflows/import",
        headers=auth_headers,
        json={"document": doc, "name": "Renamed Import", "active": False},
    )
    assert imp.status_code == 201, imp.text
    assert imp.json()["name"] == "Renamed Import"
    assert imp.json()["active"] is False
