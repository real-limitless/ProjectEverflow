"""RAG: reindex, retrieve, collections, eval, research promote."""

import pytest
from httpx import AsyncClient


async def _project(client: AsyncClient, headers: dict[str, str]) -> str:
    org = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "RAG Org", "slug": "rag-org"},
    )
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]
    proj = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=headers,
        json={"name": "RAG App", "slug": "rag-app", "description": "knowledge"},
    )
    assert proj.status_code == 201, proj.text
    return proj.json()["id"]


@pytest.mark.asyncio
async def test_reindex_and_retrieve(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project_id = await _project(client, auth_headers)
    create = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/canvases",
        headers=auth_headers,
        json={
            "name": "pgvector notes",
            "content_md": (
                "# Embeddings\n\nEverflow stores knowledge chunks for retrieval.\n\n"
                "## Knowledge key\n\nThe password is apple1234\n"
            ),
            "origin": "created",
        },
    )
    assert create.status_code == 201, create.text
    canvas_id = create.json()["id"]

    reindexed = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/canvases/{canvas_id}/reindex",
        headers=auth_headers,
    )
    assert reindexed.status_code == 200, reindexed.text
    assert reindexed.json()["status"] == "indexed"
    assert (reindexed.json()["chunks"] or 0) >= 1

    retrieved = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/retrieve",
        headers=auth_headers,
        json={"query": "knowledge chunks retrieval", "top_k": 3},
    )
    assert retrieved.status_code == 200, retrieved.text
    hits = retrieved.json()["hits"]
    assert hits
    assert hits[0]["canvas_id"] == canvas_id

    secret = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/retrieve",
        headers=auth_headers,
        json={"query": "knowledge key password", "top_k": 3},
    )
    assert secret.status_code == 200, secret.text
    secret_hits = secret.json()["hits"]
    assert secret_hits
    joined = " ".join(h["text"] for h in secret_hits)
    assert "apple1234" in joined


@pytest.mark.asyncio
async def test_list_repairs_stuck_chunking_status(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Chunks present but status=chunking should heal to indexed on list."""
    project_id = await _project(client, auth_headers)
    create = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/canvases",
        headers=auth_headers,
        json={
            "name": "stuck status",
            "content_md": "# Doc\n\nSome body text for indexing.\n",
            "origin": "created",
        },
    )
    assert create.status_code == 201, create.text
    canvas_id = create.json()["id"]
    reindexed = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/canvases/{canvas_id}/reindex",
        headers=auth_headers,
    )
    assert reindexed.status_code == 200
    # Simulate crash mid-reindex UI state
    stuck = await client.patch(
        f"/api/v1/projects/{project_id}/knowledge/canvases/{canvas_id}",
        headers=auth_headers,
        json={"status": "chunking"},
    )
    assert stuck.status_code == 200
    assert stuck.json()["status"] == "chunking"

    listed = await client.get(
        f"/api/v1/projects/{project_id}/knowledge/canvases",
        headers=auth_headers,
    )
    assert listed.status_code == 200
    row = next(c for c in listed.json() if c["id"] == canvas_id)
    assert row["status"] == "indexed"
    assert (row.get("chunks") or 0) >= 1


@pytest.mark.asyncio
async def test_research_promote_and_eval(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    project_id = await _project(client, auth_headers)
    promote = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/research/promote",
        headers=auth_headers,
        json={
            "title": "Claims from article",
            "mode": "claims",
            "source_url": "https://example.com/doc",
            "thread": [
                {"role": "user", "text": "What is the main claim?"},
                {"role": "assistant", "text": "Everflow uses project-scoped knowledge canvases."},
            ],
            "article_markdown": "# Doc\n\nProject knowledge canvases power RAG.",
        },
    )
    assert promote.status_code == 201, promote.text
    canvas_id = promote.json()["id"]
    assert promote.json()["origin"] == "research"
    assert promote.json()["status"] == "indexed"

    eset = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/eval-sets",
        headers=auth_headers,
        json={
            "name": "Smoke eval",
            "questions": [
                {
                    "question": "project-scoped knowledge canvases",
                    "expected_canvas_ids": [canvas_id],
                }
            ],
        },
    )
    assert eset.status_code == 201, eset.text
    run = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/eval-sets/{eset.json()['id']}/run",
        headers=auth_headers,
    )
    assert run.status_code == 200, run.text
    assert run.json()["total"] == 1
    assert run.json()["hits"] == 1
    assert run.json()["score"] == 1.0


@pytest.mark.asyncio
async def test_collections_and_links(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project_id = await _project(client, auth_headers)
    col = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/collections",
        headers=auth_headers,
        json={"name": "Team docs", "visibility": "team"},
    )
    assert col.status_code == 201, col.text
    collection_id = col.json()["id"]

    agent = await client.post(
        f"/api/v1/projects/{project_id}/agents",
        headers=auth_headers,
        json={"name": "Researcher", "role": "research", "system_prompt": "Search knowledge."},
    )
    assert agent.status_code == 201, agent.text
    agent_id = agent.json()["id"]

    grant = await client.put(
        f"/api/v1/projects/{project_id}/knowledge/collections/{collection_id}/grants",
        headers=auth_headers,
        json={"agent_id": agent_id, "can_retrieve": True, "can_write": False},
    )
    assert grant.status_code == 200, grant.text
    assert grant.json()["can_retrieve"] is True

    link = await client.post(
        f"/api/v1/projects/{project_id}/knowledge/links",
        headers=auth_headers,
        json={
            "from_type": "agent",
            "from_id": agent_id,
            "to_type": "collection",
            "to_id": collection_id,
            "rel": "maps_to",
        },
    )
    assert link.status_code == 201, link.text
    links = await client.get(
        f"/api/v1/projects/{project_id}/knowledge/links",
        headers=auth_headers,
    )
    assert links.status_code == 200
    assert len(links.json()) >= 1
