"""Project-scoped knowledge canvas CRUD."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal, get_principal, get_project_for_principal
from app.db.session import get_async_session
from app.models.knowledge import KnowledgeCanvas
from app.models.project import Project
from app.schemas.knowledge import (
    KnowledgeCanvasCreate,
    KnowledgeCanvasRead,
    KnowledgeCanvasSummary,
    KnowledgeCanvasUpdate,
)

router = APIRouter(tags=["knowledge"])


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
