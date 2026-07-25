"""Project-scoped knowledge canvas CRUD, RAG, web, collections, graph, eval."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.core.principal import Principal, get_principal, get_project_for_principal
from app.db.session import get_async_session
from app.models.knowledge import (
    AgentCollectionGrant,
    KnowledgeCanvas,
    KnowledgeCanvasVersion,
    KnowledgeCollection,
    KnowledgeEvalQuestion,
    KnowledgeEvalSet,
    KnowledgeLink,
    KnowledgeMindMap,
)
from app.models.project import Project
from app.schemas.knowledge import (
    AgentCollectionGrantRead,
    AgentCollectionGrantUpsert,
    KnowledgeCanvasCreate,
    KnowledgeCanvasRead,
    KnowledgeCanvasSummary,
    KnowledgeCanvasUpdate,
    KnowledgeCollectionCreate,
    KnowledgeCollectionRead,
    KnowledgeCollectionUpdate,
    KnowledgeEvalQuestionResult,
    KnowledgeEvalRunResult,
    KnowledgeEvalSetCreate,
    KnowledgeEvalSetRead,
    KnowledgeLinkCreate,
    KnowledgeLinkRead,
    KnowledgeMindMapCreate,
    KnowledgeMindMapRead,
    KnowledgeMindMapUpdate,
    KnowledgeRetrieveRequest,
    KnowledgeRetrieveResult,
    KnowledgeVersionRead,
    RefreshSourceResult,
    RepoIndexRequest,
    RepoIndexResult,
    ResearchPromoteRequest,
    WebReadRequest,
    WebReadResult,
    WebSearchHit,
)
from app.services.knowledge_embed import content_hash, reindex_canvas, repair_canvas_index_status
from app.services.knowledge_repo import index_sandbox_docs
from app.services.knowledge_retrieve import retrieve
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError
from app.services.web_read import WebReadError, fetch_reader_content

router = APIRouter(tags=["knowledge"])


async def _searxng_web_search(base_url: str, q: str) -> list[WebSearchHit]:
    root = (base_url or "").rstrip("/")
    if not root:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web search unavailable: SEARXNG_URL is not configured",
        )
    url = f"{root}/search"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url, params={"q": q, "format": "json"})
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Web search unavailable: cannot reach SearXNG ({exc})",
        ) from exc

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Web search unavailable: SearXNG returned HTTP {resp.status_code}",
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web search unavailable: SearXNG returned invalid JSON",
        ) from exc

    raw_results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(raw_results, list):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Web search unavailable: unexpected SearXNG response",
        )

    hits: list[WebSearchHit] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        link = str(item.get("url") or "").strip()
        snippet = str(item.get("content") or item.get("snippet") or "").strip()
        if not title and not link:
            continue
        hit_id = sha1(f"{link}\0{title}".encode("utf-8")).hexdigest()[:16]
        hits.append(
            WebSearchHit(
                id=hit_id,
                title=title or link,
                url=link,
                snippet=snippet,
            )
        )
    return hits


async def _get_canvas_for_project(
    session: AsyncSession,
    project_id: UUID,
    canvas_id: UUID,
) -> KnowledgeCanvas:
    result = await session.execute(
        select(KnowledgeCanvas).where(
            KnowledgeCanvas.id == canvas_id,
            KnowledgeCanvas.project_id == project_id,
        )
    )
    canvas = result.scalar_one_or_none()
    if canvas is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canvas not found")
    return canvas


async def _snapshot(
    session: AsyncSession,
    canvas: KnowledgeCanvas,
    *,
    user_id: UUID | None,
    label: str | None = None,
) -> None:
    session.add(
        KnowledgeCanvasVersion(
            canvas_id=canvas.id,
            content_md=canvas.content_md or "",
            created_by=user_id,
            label=label,
        )
    )


# ── Web search / read ─────────────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/knowledge/web-search",
    response_model=list[WebSearchHit],
)
async def knowledge_web_search(
    q: str = Query(..., min_length=1, max_length=500),
    _project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings),
) -> list[WebSearchHit]:
    principal.require_scope("knowledge:read")
    return await _searxng_web_search(settings.searxng_url, q.strip())


@router.post(
    "/projects/{project_id}/knowledge/web-read",
    response_model=WebReadResult,
)
async def knowledge_web_read(
    body: WebReadRequest,
    _project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
) -> WebReadResult:
    principal.require_scope("knowledge:read")
    try:
        data = await fetch_reader_content(body.url)
    except WebReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return WebReadResult(**data)


# ── Retrieve ──────────────────────────────────────────────────────────────────


@router.post(
    "/projects/{project_id}/knowledge/retrieve",
    response_model=KnowledgeRetrieveResult,
)
async def knowledge_retrieve(
    body: KnowledgeRetrieveRequest,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeRetrieveResult:
    principal.require_scope("knowledge:read")
    hits = await retrieve(
        session,
        project_id=project.id,
        query=body.query,
        top_k=body.top_k,
        collection_ids=body.collection_ids,
        agent_id=body.agent_id,
        user_id=principal.user.id,
    )
    return KnowledgeRetrieveResult(hits=hits)


# ── Canvases ──────────────────────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/knowledge/canvases",
    response_model=list[KnowledgeCanvasSummary],
)
async def list_canvases(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[KnowledgeCanvas]:
    principal.require_scope("knowledge:read")
    result = await session.execute(
        select(KnowledgeCanvas)
        .where(KnowledgeCanvas.project_id == project.id)
        .order_by(KnowledgeCanvas.updated_at.desc())
    )
    canvases = list(result.scalars().all())
    # Heal stuck chunking/embedding when chunks already exist (crash mid-reindex).
    for canvas in canvases:
        if canvas.status in ("chunking", "embedding"):
            await repair_canvas_index_status(session, canvas)
    return canvases


@router.post(
    "/projects/{project_id}/knowledge/canvases",
    response_model=KnowledgeCanvasRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_canvas(
    body: KnowledgeCanvasCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeCanvas:
    principal.require_scope("knowledge:rw")
    source_url = body.source_url
    if not source_url and body.origin == "web" and body.description:
        # Common UI pattern: description holds the URL for web pins
        if body.description.startswith("http://") or body.description.startswith("https://"):
            source_url = body.description
    canvas = KnowledgeCanvas(
        project_id=project.id,
        collection_id=body.collection_id,
        name=body.name.strip(),
        description=body.description,
        content_md=body.content_md,
        origin=body.origin,
        status=body.status,
        mime=body.mime,
        size_label=body.size_label,
        source_url=source_url,
        repo_path=body.repo_path,
        content_hash=content_hash(body.content_md or ""),
        last_fetched_at=datetime.now(timezone.utc) if source_url else None,
        created_by=principal.user.id,
    )
    session.add(canvas)
    await session.commit()
    await session.refresh(canvas)
    await _snapshot(session, canvas, user_id=principal.user.id, label="create")
    if source_url:
        session.add(
            KnowledgeLink(
                project_id=project.id,
                from_type="web",
                from_id=source_url[:64],
                to_type="canvas",
                to_id=str(canvas.id),
                rel="derived_from",
            )
        )
    await session.commit()
    await session.refresh(canvas)
    return canvas


@router.get(
    "/projects/{project_id}/knowledge/canvases/{canvas_id}",
    response_model=KnowledgeCanvasRead,
)
async def get_canvas(
    canvas_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeCanvas:
    principal.require_scope("knowledge:read")
    canvas = await _get_canvas_for_project(session, project.id, canvas_id)
    if canvas.status in ("chunking", "embedding"):
        canvas = await repair_canvas_index_status(session, canvas)
    return canvas


@router.patch(
    "/projects/{project_id}/knowledge/canvases/{canvas_id}",
    response_model=KnowledgeCanvasRead,
)
async def update_canvas(
    canvas_id: UUID,
    body: KnowledgeCanvasUpdate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeCanvas:
    principal.require_scope("knowledge:rw")
    canvas = await _get_canvas_for_project(session, project.id, canvas_id)
    data = body.model_dump(exclude_unset=True)
    content_changed = "content_md" in data and data["content_md"] != canvas.content_md

    if "name" in data and data["name"] is not None:
        canvas.name = data["name"].strip()
    if "description" in data:
        canvas.description = data["description"]
    if "content_md" in data and data["content_md"] is not None:
        canvas.content_md = data["content_md"]
        canvas.content_hash = content_hash(canvas.content_md)
    if "origin" in data and data["origin"] is not None:
        canvas.origin = data["origin"]
    if "status" in data and data["status"] is not None:
        canvas.status = data["status"]
    elif content_changed and canvas.status == "indexed":
        canvas.status = "stale"
    if "chunks" in data:
        canvas.chunks = data["chunks"]
    if "mime" in data:
        canvas.mime = data["mime"]
    if "size_label" in data:
        canvas.size_label = data["size_label"]
    if "collection_id" in data:
        canvas.collection_id = data["collection_id"]
    if "source_url" in data:
        canvas.source_url = data["source_url"]
    if "repo_path" in data:
        canvas.repo_path = data["repo_path"]

    if content_changed:
        await _snapshot(session, canvas, user_id=principal.user.id, label="edit")

    await session.commit()
    await session.refresh(canvas)
    return canvas


@router.delete(
    "/projects/{project_id}/knowledge/canvases/{canvas_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_canvas(
    canvas_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("knowledge:rw")
    canvas = await _get_canvas_for_project(session, project.id, canvas_id)
    await session.delete(canvas)
    await session.commit()


@router.post(
    "/projects/{project_id}/knowledge/canvases/{canvas_id}/reindex",
    response_model=KnowledgeCanvasRead,
)
async def reindex_canvas_endpoint(
    canvas_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeCanvas:
    principal.require_scope("knowledge:rw")
    canvas = await _get_canvas_for_project(session, project.id, canvas_id)
    return await reindex_canvas(session, canvas)


@router.post(
    "/projects/{project_id}/knowledge/canvases/{canvas_id}/refresh-source",
    response_model=RefreshSourceResult,
)
async def refresh_canvas_source(
    canvas_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> RefreshSourceResult:
    principal.require_scope("knowledge:rw")
    canvas = await _get_canvas_for_project(session, project.id, canvas_id)
    if not canvas.source_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Canvas has no source_url to refresh",
        )
    previous = canvas.content_hash
    try:
        data = await fetch_reader_content(canvas.source_url)
    except WebReadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    new_md = data["markdown"]
    new_hash = content_hash(new_md)
    changed = new_hash != previous
    if changed:
        await _snapshot(session, canvas, user_id=principal.user.id, label="pre-refresh")
        canvas.content_md = new_md
        if data.get("title") and not canvas.name:
            canvas.name = str(data["title"])[:200]
        canvas.content_hash = new_hash
        canvas.status = "stale" if canvas.status == "indexed" else canvas.status
    canvas.last_fetched_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(canvas)
    if changed:
        canvas = await reindex_canvas(session, canvas)
    return RefreshSourceResult(
        canvas=KnowledgeCanvasRead.model_validate(canvas),
        changed=changed,
        previous_hash=previous,
        new_hash=new_hash,
    )


@router.get(
    "/projects/{project_id}/knowledge/canvases/{canvas_id}/versions",
    response_model=list[KnowledgeVersionRead],
)
async def list_canvas_versions(
    canvas_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[KnowledgeCanvasVersion]:
    principal.require_scope("knowledge:read")
    await _get_canvas_for_project(session, project.id, canvas_id)
    result = await session.execute(
        select(KnowledgeCanvasVersion)
        .where(KnowledgeCanvasVersion.canvas_id == canvas_id)
        .order_by(KnowledgeCanvasVersion.created_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


# ── Research promote ──────────────────────────────────────────────────────────


@router.post(
    "/projects/{project_id}/knowledge/research/promote",
    response_model=KnowledgeCanvasRead,
    status_code=status.HTTP_201_CREATED,
)
async def promote_research(
    body: ResearchPromoteRequest,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeCanvas:
    principal.require_scope("knowledge:rw")
    lines: list[str] = [f"# {body.title.strip()}", ""]
    if body.source_url:
        lines.append(f"Source: {body.source_url}")
        lines.append("")
    if body.mode == "claims":
        lines.append("## Claims")
        lines.append("")
        for turn in body.thread:
            if turn.get("role") == "assistant":
                text = str(turn.get("text") or turn.get("content") or "").strip()
                if text:
                    lines.append(f"- {text}")
        lines.append("")
        lines.append("## Open questions")
        lines.append("")
        for turn in body.thread:
            if turn.get("role") == "user":
                text = str(turn.get("text") or turn.get("content") or "").strip()
                if text:
                    lines.append(f"- {text}")
        if body.article_markdown:
            lines.append("")
            lines.append("## Article excerpts")
            lines.append("")
            lines.append(body.article_markdown[:4000])
    else:
        lines.append("## Research thread")
        lines.append("")
        for turn in body.thread:
            role = str(turn.get("role") or "user")
            text = str(turn.get("text") or turn.get("content") or "").strip()
            if text:
                label = "You" if role == "user" else "Research"
                lines.append(f"**{label}:** {text}")
                lines.append("")
        if body.article_markdown:
            lines.append("## Source article")
            lines.append("")
            lines.append(body.article_markdown[:6000])

    md = "\n".join(lines).strip() + "\n"
    canvas = KnowledgeCanvas(
        project_id=project.id,
        name=body.title.strip()[:200],
        description=body.source_url,
        content_md=md,
        origin="research",
        status="ready",
        source_url=body.source_url,
        content_hash=content_hash(md),
        last_fetched_at=datetime.now(timezone.utc) if body.source_url else None,
        created_by=principal.user.id,
    )
    session.add(canvas)
    await session.commit()
    await session.refresh(canvas)
    await _snapshot(session, canvas, user_id=principal.user.id, label="research-promote")
    if body.source_url:
        session.add(
            KnowledgeLink(
                project_id=project.id,
                from_type="web",
                from_id=body.source_url[:64],
                to_type="canvas",
                to_id=str(canvas.id),
                rel="derived_from",
            )
        )
    await session.commit()
    canvas = await reindex_canvas(session, canvas)
    return canvas


# ── Repo index ────────────────────────────────────────────────────────────────


@router.post(
    "/projects/{project_id}/knowledge/index-repo",
    response_model=RepoIndexResult,
)
async def index_repo(
    body: RepoIndexRequest,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> RepoIndexResult:
    principal.require_scope("knowledge:rw")
    client = SandboxAgentClient(settings)
    try:
        result = await index_sandbox_docs(
            session,
            project=project,
            agent=client,
            created_by=principal.user.id,
            collection_name=body.collection_name,
            path_globs=body.paths,
        )
    except SandboxAgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    return RepoIndexResult(
        created=int(result["created"]),
        updated=int(result["updated"]),
        skipped=int(result["skipped"]),
        canvas_ids=list(result["canvas_ids"]),  # type: ignore[arg-type]
    )


# ── Collections + ACL ─────────────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/knowledge/collections",
    response_model=list[KnowledgeCollectionRead],
)
async def list_collections(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[KnowledgeCollection]:
    principal.require_scope("knowledge:read")
    result = await session.execute(
        select(KnowledgeCollection)
        .where(KnowledgeCollection.project_id == project.id)
        .order_by(KnowledgeCollection.name.asc())
    )
    return list(result.scalars().all())


@router.post(
    "/projects/{project_id}/knowledge/collections",
    response_model=KnowledgeCollectionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_collection(
    body: KnowledgeCollectionCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeCollection:
    principal.require_scope("knowledge:rw")
    owner = body.owner_user_id
    if body.visibility == "personal" and owner is None:
        owner = principal.user.id
    col = KnowledgeCollection(
        project_id=project.id,
        name=body.name.strip(),
        visibility=body.visibility,
        owner_user_id=owner,
    )
    session.add(col)
    await session.commit()
    await session.refresh(col)
    return col


@router.patch(
    "/projects/{project_id}/knowledge/collections/{collection_id}",
    response_model=KnowledgeCollectionRead,
)
async def update_collection(
    collection_id: UUID,
    body: KnowledgeCollectionUpdate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeCollection:
    principal.require_scope("knowledge:rw")
    result = await session.execute(
        select(KnowledgeCollection).where(
            KnowledgeCollection.id == collection_id,
            KnowledgeCollection.project_id == project.id,
        )
    )
    col = result.scalar_one_or_none()
    if col is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        col.name = data["name"].strip()
    if "visibility" in data and data["visibility"] is not None:
        col.visibility = data["visibility"]
    await session.commit()
    await session.refresh(col)
    return col


@router.put(
    "/projects/{project_id}/knowledge/collections/{collection_id}/grants",
    response_model=AgentCollectionGrantRead,
)
async def upsert_grant(
    collection_id: UUID,
    body: AgentCollectionGrantUpsert,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> AgentCollectionGrant:
    principal.require_scope("knowledge:rw")
    col = await session.execute(
        select(KnowledgeCollection).where(
            KnowledgeCollection.id == collection_id,
            KnowledgeCollection.project_id == project.id,
        )
    )
    if col.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    existing = await session.execute(
        select(AgentCollectionGrant).where(
            AgentCollectionGrant.collection_id == collection_id,
            AgentCollectionGrant.agent_id == body.agent_id,
        )
    )
    grant = existing.scalar_one_or_none()
    if grant is None:
        grant = AgentCollectionGrant(
            agent_id=body.agent_id,
            collection_id=collection_id,
            can_retrieve=body.can_retrieve,
            can_write=body.can_write,
        )
        session.add(grant)
    else:
        grant.can_retrieve = body.can_retrieve
        grant.can_write = body.can_write
    await session.commit()
    await session.refresh(grant)
    return grant


@router.get(
    "/projects/{project_id}/knowledge/collections/{collection_id}/grants",
    response_model=list[AgentCollectionGrantRead],
)
async def list_grants(
    collection_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[AgentCollectionGrant]:
    principal.require_scope("knowledge:read")
    result = await session.execute(
        select(AgentCollectionGrant).where(
            AgentCollectionGrant.collection_id == collection_id,
        )
    )
    return list(result.scalars().all())


# ── Graph / mind maps ─────────────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/knowledge/links",
    response_model=list[KnowledgeLinkRead],
)
async def list_links(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[KnowledgeLink]:
    principal.require_scope("knowledge:read")
    result = await session.execute(
        select(KnowledgeLink)
        .where(KnowledgeLink.project_id == project.id)
        .order_by(KnowledgeLink.created_at.desc())
        .limit(500)
    )
    return list(result.scalars().all())


@router.post(
    "/projects/{project_id}/knowledge/links",
    response_model=KnowledgeLinkRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_link(
    body: KnowledgeLinkCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeLink:
    principal.require_scope("knowledge:rw")
    link = KnowledgeLink(
        project_id=project.id,
        from_type=body.from_type,
        from_id=body.from_id,
        to_type=body.to_type,
        to_id=body.to_id,
        rel=body.rel,
    )
    session.add(link)
    await session.commit()
    await session.refresh(link)
    return link


@router.get(
    "/projects/{project_id}/knowledge/mind-maps",
    response_model=list[KnowledgeMindMapRead],
)
async def list_mind_maps(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[KnowledgeMindMap]:
    principal.require_scope("knowledge:read")
    result = await session.execute(
        select(KnowledgeMindMap)
        .where(KnowledgeMindMap.project_id == project.id)
        .order_by(KnowledgeMindMap.updated_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/projects/{project_id}/knowledge/mind-maps",
    response_model=KnowledgeMindMapRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_mind_map(
    body: KnowledgeMindMapCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeMindMap:
    principal.require_scope("knowledge:rw")
    mm = KnowledgeMindMap(
        project_id=project.id,
        name=body.name.strip(),
        mermaid=body.mermaid or "",
        created_by=principal.user.id,
    )
    session.add(mm)
    await session.commit()
    await session.refresh(mm)
    return mm


@router.patch(
    "/projects/{project_id}/knowledge/mind-maps/{mind_map_id}",
    response_model=KnowledgeMindMapRead,
)
async def update_mind_map(
    mind_map_id: UUID,
    body: KnowledgeMindMapUpdate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeMindMap:
    principal.require_scope("knowledge:rw")
    result = await session.execute(
        select(KnowledgeMindMap).where(
            KnowledgeMindMap.id == mind_map_id,
            KnowledgeMindMap.project_id == project.id,
        )
    )
    mm = result.scalar_one_or_none()
    if mm is None:
        raise HTTPException(status_code=404, detail="Mind map not found")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        mm.name = data["name"].strip()
    if "mermaid" in data and data["mermaid"] is not None:
        mm.mermaid = data["mermaid"]
    await session.commit()
    await session.refresh(mm)
    return mm


@router.delete(
    "/projects/{project_id}/knowledge/mind-maps/{mind_map_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_mind_map(
    mind_map_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("knowledge:rw")
    result = await session.execute(
        select(KnowledgeMindMap).where(
            KnowledgeMindMap.id == mind_map_id,
            KnowledgeMindMap.project_id == project.id,
        )
    )
    mm = result.scalar_one_or_none()
    if mm is None:
        raise HTTPException(status_code=404, detail="Mind map not found")
    await session.delete(mm)
    await session.commit()


# ── Eval ──────────────────────────────────────────────────────────────────────


@router.get(
    "/projects/{project_id}/knowledge/eval-sets",
    response_model=list[KnowledgeEvalSetRead],
)
async def list_eval_sets(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[KnowledgeEvalSet]:
    principal.require_scope("knowledge:read")
    result = await session.execute(
        select(KnowledgeEvalSet)
        .where(KnowledgeEvalSet.project_id == project.id)
        .options(selectinload(KnowledgeEvalSet.questions))
        .order_by(KnowledgeEvalSet.updated_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/projects/{project_id}/knowledge/eval-sets",
    response_model=KnowledgeEvalSetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_eval_set(
    body: KnowledgeEvalSetCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeEvalSet:
    principal.require_scope("knowledge:rw")
    eset = KnowledgeEvalSet(
        project_id=project.id,
        name=body.name.strip(),
        collection_id=body.collection_id,
    )
    session.add(eset)
    await session.flush()
    for q in body.questions:
        session.add(
            KnowledgeEvalQuestion(
                eval_set_id=eset.id,
                question=q.question,
                expected_canvas_ids=q.expected_canvas_ids,
                expected_notes=q.expected_notes,
            )
        )
    await session.commit()
    result = await session.execute(
        select(KnowledgeEvalSet)
        .where(KnowledgeEvalSet.id == eset.id)
        .options(selectinload(KnowledgeEvalSet.questions))
    )
    return result.scalar_one()


@router.post(
    "/projects/{project_id}/knowledge/eval-sets/{eval_set_id}/run",
    response_model=KnowledgeEvalRunResult,
)
async def run_eval_set(
    eval_set_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> KnowledgeEvalRunResult:
    principal.require_scope("knowledge:read")
    result = await session.execute(
        select(KnowledgeEvalSet)
        .where(
            KnowledgeEvalSet.id == eval_set_id,
            KnowledgeEvalSet.project_id == project.id,
        )
        .options(selectinload(KnowledgeEvalSet.questions))
    )
    eset = result.scalar_one_or_none()
    if eset is None:
        raise HTTPException(status_code=404, detail="Eval set not found")

    results: list[KnowledgeEvalQuestionResult] = []
    hits_n = 0
    for q in eset.questions:
        expected = [str(x) for x in (q.expected_canvas_ids or [])]
        coll_ids = [eset.collection_id] if eset.collection_id else None
        hits = await retrieve(
            session,
            project_id=project.id,
            query=q.question,
            top_k=5,
            collection_ids=coll_ids,
            agent_id=None,
            user_id=principal.user.id,
        )
        retrieved = [str(h.canvas_id) for h in hits]
        hit = bool(expected) and any(e in retrieved for e in expected)
        if hit or (not expected and hits):
            # If no expected ids, count as hit when anything retrieved
            if expected:
                hits_n += 1 if hit else 0
            else:
                hits_n += 1 if hits else 0
                hit = bool(hits)
        results.append(
            KnowledgeEvalQuestionResult(
                question_id=q.id,
                question=q.question,
                hit=hit,
                expected_canvas_ids=expected,
                retrieved_canvas_ids=retrieved,
                top_score=hits[0].score if hits else None,
            )
        )

    total = len(eset.questions) or 1
    score = hits_n / total
    eset.last_score = score
    eset.last_run_at = datetime.now(timezone.utc)
    await session.commit()
    return KnowledgeEvalRunResult(
        eval_set_id=eset.id,
        score=round(score, 4),
        total=len(eset.questions),
        hits=hits_n,
        results=results,
    )
