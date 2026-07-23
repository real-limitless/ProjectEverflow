"""Provider credential request/response schemas (never include raw secrets)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProviderName = Literal["openrouter", "openai", "anthropic", "xai", "custom"]
ScopeName = Literal["chat", "embed", "ocr", "*"]


class ProviderCredentialCreate(BaseModel):
    provider: ProviderName
    api_key: str = Field(min_length=1, max_length=4096)
    label: str | None = Field(default=None, max_length=120)
    scopes: list[ScopeName] | None = None
    is_default: bool = True

    @field_validator("api_key")
    @classmethod
    def strip_key(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("api_key is required")
        return s

    @field_validator("label")
    @classmethod
    def strip_label(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class ProviderCredentialUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    scopes: list[ScopeName] | None = None
    is_default: bool | None = None
    # Optional key rotation
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)

    @field_validator("api_key")
    @classmethod
    def strip_key(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("api_key cannot be empty")
        return s

    @field_validator("label")
    @classmethod
    def strip_label(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        return s or None


class ProviderCredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_type: Literal["user", "project"]
    owner_id: UUID
    provider: str
    label: str | None = None
    scopes: list[str]
    is_default: bool
    key_hint: str | None = None
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None


class ProviderCatalogItem(BaseModel):
    id: str
    name: str
    description: str
    scopes: list[str]
