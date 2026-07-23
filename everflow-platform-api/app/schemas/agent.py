"""Project agent definition request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectAgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str = Field(default="general", min_length=1, max_length=120)
    description: str = ""
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    active: bool = True

    @field_validator("tools", mode="before")
    @classmethod
    def coerce_tools(cls, v: object) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise TypeError("tools must be a list of strings")
        return [str(t).strip() for t in v if str(t).strip()]


class ProjectAgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None
    active: bool | None = None

    @field_validator("tools", mode="before")
    @classmethod
    def coerce_tools(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            raise TypeError("tools must be a list of strings")
        return [str(t).strip() for t in v if str(t).strip()]


class ProjectAgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    role: str
    description: str
    system_prompt: str
    tools: list[str] = Field(default_factory=list)
    active: bool
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("tools", mode="before")
    @classmethod
    def coerce_tools_out(cls, v: object) -> list[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        return [str(t) for t in v]
