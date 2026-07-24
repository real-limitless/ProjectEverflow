"""AI usage ingest and summary schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AiUsageEventCreate(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    message_id: str = Field(min_length=1, max_length=200)
    provider: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=200)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    ttft_ms: int | None = Field(default=None, ge=0)
    occurred_at: datetime | None = None
    completed: bool = False

    @field_validator("session_id", "message_id", mode="before")
    @classmethod
    def strip_ids(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("provider", "model", mode="before")
    @classmethod
    def strip_optional(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            return s or None
        return v

    @model_validator(mode="after")
    def compute_total(self) -> "AiUsageEventCreate":
        if self.total_tokens is None:
            self.total_tokens = (
                self.input_tokens
                + self.output_tokens
                + self.reasoning_tokens
                + self.cache_read_tokens
            )
        return self


class AiUsageEventBatchCreate(BaseModel):
    events: list[AiUsageEventCreate] = Field(min_length=1, max_length=100)


class AiUsageEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    project_id: UUID
    user_id: UUID
    session_id: str
    message_id: str
    provider: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_tokens: int
    duration_ms: int | None
    ttft_ms: int | None
    occurred_at: datetime
    created_at: datetime


class AiUsageBatchResult(BaseModel):
    accepted: int
    skipped: int
    events: list[AiUsageEventRead]


class AiUsageTotals(BaseModel):
    messages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    projects: int = 0
    users: int = 0
    sessions: int = 0


class AiUsageDailyPoint(BaseModel):
    date: str
    tokens: int
    messages: int


class AiUsageByModel(BaseModel):
    provider: str | None
    model: str | None
    tokens: int
    messages: int


class AiUsageByProject(BaseModel):
    project_id: UUID
    project_name: str
    tokens: int
    messages: int


class AiUsageByUser(BaseModel):
    user_id: UUID
    email: str
    tokens: int
    messages: int


class AiUsageSummary(BaseModel):
    scope: Literal["me", "org"]
    from_: datetime = Field(validation_alias="from", serialization_alias="from")
    to: datetime
    totals: AiUsageTotals
    series_daily: list[AiUsageDailyPoint]
    by_model: list[AiUsageByModel]
    by_project: list[AiUsageByProject]
    by_user: list[AiUsageByUser] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)
