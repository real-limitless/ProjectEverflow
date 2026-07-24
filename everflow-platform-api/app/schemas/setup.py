"""First-run setup schemas."""

from pydantic import BaseModel, EmailStr, Field


class SetupStatus(BaseModel):
    needs_setup: bool
    environment: str
    warnings: list[str] = Field(default_factory=list)
    sandbox: dict | None = None
    oauth: dict[str, bool] = Field(default_factory=dict)


class SetupBootstrapRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    org_name: str = Field(min_length=1, max_length=200)
    org_slug: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )


class SetupBootstrapResponse(BaseModel):
    user_id: str
    email: str
    org_id: str
    org_slug: str
    access_token: str
    token_type: str = "bearer"
