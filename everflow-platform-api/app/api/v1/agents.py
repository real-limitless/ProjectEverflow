"""Project-scoped agent definition CRUD (studio Agents panel)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import Principal, get_principal, get_project_for_principal
from app.db.session import get_async_session
from app.models.agent import ProjectAgent
from app.models.project import Project
from app.schemas.agent import ProjectAgentCreate, ProjectAgentRead, ProjectAgentUpdate

router = APIRouter(tags=["agents"])


async def _get_agent_for_project(
    session: AsyncSession,
    project_id: UUID,
    agent_id: UUID,
) -> ProjectAgent:
    result = await session.execute(
        select(ProjectAgent).where(
            ProjectAgent.id == agent_id,
            ProjectAgent.project_id == project_id,
        )
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent


@router.get(
    "/projects/{project_id}/agents",
    response_model=list[ProjectAgentRead],
)
async def list_agents(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[ProjectAgent]:
    principal.require_scope("agents:read")
    result = await session.execute(
        select(ProjectAgent)
        .where(ProjectAgent.project_id == project.id)
        .order_by(ProjectAgent.updated_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/projects/{project_id}/agents",
    response_model=ProjectAgentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    body: ProjectAgentCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> ProjectAgent:
    principal.require_scope("agents:rw")
    agent = ProjectAgent(
        project_id=project.id,
        name=body.name.strip(),
        role=body.role.strip(),
        description=body.description,
        system_prompt=body.system_prompt,
        tools=list(body.tools),
        active=body.active,
        created_by=principal.user.id,
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


@router.get(
    "/projects/{project_id}/agents/{agent_id}",
    response_model=ProjectAgentRead,
)
async def get_agent(
    agent_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> ProjectAgent:
    principal.require_scope("agents:read")
    return await _get_agent_for_project(session, project.id, agent_id)


@router.patch(
    "/projects/{project_id}/agents/{agent_id}",
    response_model=ProjectAgentRead,
)
async def update_agent(
    agent_id: UUID,
    body: ProjectAgentUpdate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> ProjectAgent:
    principal.require_scope("agents:rw")
    agent = await _get_agent_for_project(session, project.id, agent_id)
    data = body.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        agent.name = data["name"].strip()
    if "role" in data and data["role"] is not None:
        agent.role = data["role"].strip()
    if "description" in data and data["description"] is not None:
        agent.description = data["description"]
    if "system_prompt" in data and data["system_prompt"] is not None:
        agent.system_prompt = data["system_prompt"]
    if "tools" in data and data["tools"] is not None:
        agent.tools = list(data["tools"])
    if "active" in data and data["active"] is not None:
        agent.active = data["active"]

    await session.commit()
    await session.refresh(agent)
    return agent


@router.delete(
    "/projects/{project_id}/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_agent(
    agent_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("agents:rw")
    agent = await _get_agent_for_project(session, project.id, agent_id)
    await session.delete(agent)
    await session.commit()
