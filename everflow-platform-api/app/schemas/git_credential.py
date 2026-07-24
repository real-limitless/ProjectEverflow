"""Git credential vault schemas (never expose plaintext after create)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

OwnerType = Literal["user", "org", "project"]
GitProvider = Literal["github", "gitlab", "bitbucket", "custom"]


class GitCredentialCreate(BaseModel):
    provider: GitProvider = "github"
    token: str = Field(min_length=8, max_length=500)
    label: str | None = Field(default=None, max_length=120)
    scopes: str = Field(default="repo", max_length=120)
    is_default: bool = True


class GitCredentialUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    token: str | None = Field(default=None, min_length=8, max_length=500)
    scopes: str | None = Field(default=None, max_length=120)
    is_default: bool | None = None


class GitCredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_type: OwnerType
    owner_id: UUID
    provider: str
    label: str | None
    scopes: str
    is_default: bool
    key_hint: str
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None
