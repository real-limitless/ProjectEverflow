"""Project database (Postgres via sandbox) schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DatabaseStatusRead(BaseModel):
    """Connection / provisioning status for the project's sandbox database."""

    status: str = Field(
        description="ready | not_provisioned | unreachable | no_sandbox | error",
    )
    engine: str | None = None
    display_url: str | None = Field(
        default=None,
        description="Connection string with password masked for UI display",
    )
    psql_available: bool = False
    message: str | None = None
    harness_installed: bool = False


class DatabaseTableRead(BaseModel):
    name: str
    schema_name: str = "public"
    rows: int | None = None
    size: str | None = None


class DatabaseTablesRead(BaseModel):
    tables: list[DatabaseTableRead] = Field(default_factory=list)
    status: str = "ready"
    message: str | None = None


class DatabaseQueryRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=20_000)
    limit: int = Field(default=100, ge=1, le=1000)


class DatabaseQueryResult(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    error: str | None = None
