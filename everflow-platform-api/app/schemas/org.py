"""Team, seat, chart, and constitution schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

SeatKind = Literal["human", "bot"]
SeatStatus = Literal["idle", "assigned", "running", "blocked", "review", "done"]


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    mention: str | None = Field(default=None, max_length=80)
    lane: str = Field(default="line", max_length=32)
    description: str = ""


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    mention: str | None = Field(default=None, max_length=80)
    lane: str | None = Field(default=None, max_length=32)
    description: str | None = None
    conductor_seat_id: UUID | None = None


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    slug: str
    mention: str
    lane: str
    description: str
    conductor_seat_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class SeatCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    kind: SeatKind = "bot"
    role: str = Field(default="specialist", max_length=80)
    lane: str = Field(default="line", max_length=32)
    description: str = ""
    team_id: UUID | None = None
    reports_to_id: UUID | None = None
    agent_slug: str | None = Field(default=None, max_length=80)
    is_conductor: bool = False
    worktree_path: str | None = None
    budget_tokens: int = 0
    permission: dict[str, Any] | None = None
    tools: list[str] = Field(default_factory=list)
    prompt: str = ""
    skills: list[str] = Field(default_factory=list)
    preferred_models: list[str] = Field(default_factory=list)
    template: str | None = None


class SeatUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    role: str | None = None
    description: str | None = None
    team_id: UUID | None = None
    reports_to_id: UUID | None = None
    agent_slug: str | None = None
    is_conductor: bool | None = None
    paused: bool | None = None
    budget_tokens: int | None = None
    permission: dict[str, Any] | None = None
    tools: list[str] | None = None
    prompt: str | None = None
    skills: list[str] | None = None
    preferred_models: list[str] | None = None
    status: str | None = None
    worktree_path: str | None = None
    opencode_session_id: str | None = None


class SeatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    team_id: UUID | None = None
    kind: str
    slug: str
    name: str
    role: str
    lane: str
    description: str
    reports_to_id: UUID | None = None
    owner_user_id: UUID | None = None
    agent_slug: str | None = None
    is_conductor: bool
    paused: bool
    fired: bool
    opencode_session_id: str | None = None
    worktree_path: str | None = None
    budget_tokens: int
    permission: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    prompt: str = ""
    skills: list[str] = Field(default_factory=list)
    preferred_models: list[str] = Field(default_factory=list)
    status: str
    created_at: datetime
    updated_at: datetime

    @field_validator("permission", mode="before")
    @classmethod
    def coerce_permission(cls, v: object) -> dict[str, Any]:
        return dict(v) if isinstance(v, dict) else {}

    @field_validator("tools", "skills", "preferred_models", mode="before")
    @classmethod
    def coerce_str_list(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(t) for t in v]


class SeatReparent(BaseModel):
    reports_to_id: UUID | None = None


class ChartEdge(BaseModel):
    from_id: UUID
    to_id: UUID


class ChartRead(BaseModel):
    teams: list[TeamRead]
    seats: list[SeatRead]
    edges: list[ChartEdge]
    constitution_md: str = ""


class ConstitutionRead(BaseModel):
    constitution_md: str
    agents_md_note: str = (
        "AGENTS.md is the injected Everflow platform playbook. "
        "constitution.md is project law every seat must read."
    )


class ConstitutionUpdate(BaseModel):
    constitution_md: str = Field(min_length=1)


class MultiTeamExport(BaseModel):
    yaml: str
