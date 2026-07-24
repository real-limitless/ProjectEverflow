"""Organization request/response schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

OrgRole = Literal["owner", "admin", "member"]
InviteRole = Literal["admin", "member"]


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
    role: str | None = None  # caller's role when listed


class OrganizationMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    email: str | None = None
    role: str
    created_at: datetime


class OrganizationMemberUpdate(BaseModel):
    role: OrgRole


class OrganizationInviteCreate(BaseModel):
    role: InviteRole = "member"
    email: EmailStr | None = None
    expires_hours: int = Field(default=168, ge=1, le=720)


class OrganizationInviteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    role: str
    email: str | None
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime
    invite_url: str | None = None
    token: str | None = None  # plaintext only on create


class OrganizationInviteAcceptResult(BaseModel):
    organization_id: UUID
    organization_name: str
    organization_slug: str
    role: str
