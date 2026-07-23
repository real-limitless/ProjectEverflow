"""Project request/response schemas."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ProjectRepoIn(BaseModel):
    """Repository attached at project create/update time."""

    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=500)
    branch: str | None = Field(default="main", max_length=200)
    provider: Literal["github", "gitlab", "other", "none"] | None = "github"
    local_path: str | None = Field(default=None, max_length=200)
    active: bool | None = False

    @field_validator("url")
    @classmethod
    def normalize_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @field_validator("branch")
    @classmethod
    def normalize_branch(cls, v: str | None) -> str | None:
        if v is None:
            return "main"
        s = v.strip()
        return s or "main"

    @field_validator("local_path")
    @classmethod
    def normalize_local_path(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip().replace("\\", "/").lstrip("./")
        if not s or s == ".":
            return "."
        if s.startswith("/") or ".." in s.split("/"):
            raise ValueError("local_path must be a relative workspace path without '..'")
        return s


class ProjectRepoOut(BaseModel):
    id: str
    label: str
    url: str | None = None
    branch: str | None = None
    provider: str | None = None
    local_path: str | None = None
    active: bool | None = False
    clone_status: str | None = None  # pending | cloning | ready | skipped | error
    clone_error: str | None = None


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None
    repos: list[ProjectRepoIn] = Field(default_factory=list, max_length=10)
    # Harness ids (e.g. agent-opencode, db-postgres) or {id, enabled} objects
    harnesses: list[str | dict[str, Any]] | None = Field(default=None, max_length=40)

    @model_validator(mode="after")
    def ensure_one_active(self) -> "ProjectCreate":
        if not self.repos:
            return self
        if not any(r.active for r in self.repos):
            self.repos[0].active = True
        else:
            saw = False
            for r in self.repos:
                if r.active and not saw:
                    saw = True
                else:
                    r.active = False
        return self


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    description: str | None = None
    repos: list[ProjectRepoIn] | None = Field(default=None, max_length=10)
    harnesses: list[str | dict[str, Any]] | None = Field(default=None, max_length=40)
    # When True and harnesses were updated, re-run sandbox bootstrap (or recreate if not running).
    reconfigure_sandbox: bool | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    slug: str
    description: str | None
    repos: list[dict[str, Any]] = Field(default_factory=list)
    harnesses: list[Any] = Field(default_factory=list)
    sandbox_name: str | None = None
    sandbox_status: str = "pending"
    sandbox_image: str | None = None
    sandbox_error: str | None = None
    sandbox_created_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("repos", mode="before")
    @classmethod
    def default_repos(cls, v: Any) -> list[dict[str, Any]]:
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return []

    @field_validator("harnesses", mode="before")
    @classmethod
    def default_harnesses(cls, v: Any) -> list[Any]:
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return []
