"""Project-scoped knowledge canvas CRUD + web search."""

from __future__ import annotations

from hashlib import sha1
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.principal import Principal, get_principal, get_project_for_principal
from app.db.session import get_async_session
from app.models.knowledge import KnowledgeCanvas
from app.models.project import Project
from app.schemas.knowledge import (
    KnowledgeCanvasCreate,
    KnowledgeCanvasRead,
    KnowledgeCanvasSummary,
    KnowledgeCanvasUpdate,
    WebSearchHit,
)

router = APIRouter(tags=["knowledge"])


async def _searxng_web_search(base_url: str, q: str) -> list[WebSearchHit]:
    """Call SearXNG JSON search; raise HTTPException 503 if unavailable."""
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
    """Proxy web search via SearXNG for the knowledge panel."""
    principal.require_scope("knowledge:read")
    return await _searxng_web_search(settings.searxng_url, q.strip())


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
    return list(result.scalars().all())


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
    canvas = KnowledgeCanvas(
        project_id=project.id,
        name=body.name.strip(),
        description=body.description,
        content_md=body.content_md,
        origin=body.origin,
        status=body.status,
        mime=body.mime,
        size_label=body.size_label,
        created_by=principal.user.id,
    )
    session.add(canvas)
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
    return await _get_canvas_for_project(session, project.id, canvas_id)


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
