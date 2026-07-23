"""HTTP tool request/response schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


class HttpToolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    method: str = Field(default="GET", min_length=1, max_length=16)
    url_template: str = Field(min_length=1, max_length=2000)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("name is required")
        return s

    @field_validator("method")
    @classmethod
    def normalize_method(cls, v: str) -> str:
        m = v.strip().upper()
        if m not in ALLOWED_METHODS:
            raise ValueError(f"method must be one of {sorted(ALLOWED_METHODS)}")
        return m

    @field_validator("url_template")
    @classmethod
    def strip_url(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("url_template is required")
        return s


class HttpToolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    method: str | None = Field(default=None, min_length=1, max_length=16)
    url_template: str | None = Field(default=None, min_length=1, max_length=2000)
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("name cannot be empty")
        return s

    @field_validator("method")
    @classmethod
    def normalize_method(cls, v: str | None) -> str | None:
        if v is None:
            return None
        m = v.strip().upper()
        if m not in ALLOWED_METHODS:
            raise ValueError(f"method must be one of {sorted(ALLOWED_METHODS)}")
        return m

    @field_validator("url_template")
    @classmethod
    def strip_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("url_template cannot be empty")
        return s


class HttpToolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    method: str
    url_template: str
    enabled: bool
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class HttpToolExecuteRequest(BaseModel):
    """Optional path/query/header/body substitutions for url_template and the request."""

    path_params: dict[str, str] = Field(default_factory=dict)
    query: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any | None = None


class HttpToolExecuteResult(BaseModel):
    ok: bool
    status_code: int | None = None
    url: str
    method: str
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    truncated: bool = False
    error: str | None = None
    elapsed_ms: int = 0
