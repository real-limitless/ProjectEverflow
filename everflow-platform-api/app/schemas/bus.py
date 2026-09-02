"""Bus, run, and memory schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

BusVerb = Literal[
    "send_message",
    "handoff",
    "share_memory",
    "create_task",
    "depend_on",
    "ask_human",
    "report",
]


class RunCompileBody(BaseModel):
    sentence: str = Field(min_length=1)
    channel_id: UUID | None = None
    thread_id: UUID | None = None
    title: str | None = None
    start: bool = True


class RunNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    seat_id: UUID | None = None
    key: str
    label: str
    status: str
    brief: str
    result: str
    sort_order: int
    depends_on: list[str] = Field(default_factory=list)

    @field_validator("depends_on", mode="before")
    @classmethod
    def coerce_depends(cls, v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        return [str(x) for x in v]


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    channel_id: UUID | None = None
    thread_id: UUID | None = None
    title: str
    sentence: str
    status: str
    compiled_graph: dict[str, Any] = Field(default_factory=dict)
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime
    nodes: list[RunNodeRead] = Field(default_factory=list)


class RunNodePatch(BaseModel):
    status: str | None = None
    result: str | None = None
    brief: str | None = None


class BusDispatchBody(BaseModel):
    verb: BusVerb
    from_seat_id: UUID | None = None
    to_seat_id: UUID | None = None
    to_team_id: UUID | None = None
    to_channel_id: UUID | None = None
    run_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class BusEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    run_id: UUID | None = None
    verb: str
    from_seat_id: UUID | None = None
    to_seat_id: UUID | None = None
    to_team_id: UUID | None = None
    to_channel_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str
    error: str | None = None
    created_at: datetime


class MemoryUpsert(BaseModel):
    scope: Literal["seat", "team", "project", "org"]
    scope_id: str = ""
    name: str = Field(min_length=1, max_length=160)
    body: str = ""


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    scope: str
    scope_id: str
    name: str
    body: str
    created_at: datetime
    updated_at: datetime
