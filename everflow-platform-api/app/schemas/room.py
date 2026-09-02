"""Room (channel / message / thread) schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    kind: str = Field(default="channel", max_length=24)
    team_id: UUID | None = None


class ChannelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    team_id: UUID | None = None
    slug: str
    name: str
    kind: str
    created_at: datetime


class ChannelMessageCreate(BaseModel):
    body: str = Field(min_length=1)
    thread_id: UUID | None = None
    author_seat_id: UUID | None = None
    compile_run: bool = False


class ChannelMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel_id: UUID
    thread_id: UUID | None = None
    author_user_id: UUID | None = None
    author_seat_id: UUID | None = None
    body: str
    kind: str
    mentions: list[Any] = Field(default_factory=list)
    run_id: UUID | None = None
    created_at: datetime
