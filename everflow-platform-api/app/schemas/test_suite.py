"""Test suite / case request/response schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TestCaseType = Literal["unit", "e2e", "smoke"]
TestCaseStatus = Literal["passed", "failed", "skipped"]


class TestCaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    type: TestCaseType = "unit"
    command: str = ""


class TestCaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: TestCaseType | None = None
    command: str | None = None
    last_status: TestCaseStatus | None = None
    last_error: str | None = None


class TestCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    suite_id: UUID
    project_id: UUID
    name: str
    type: str
    command: str
    last_status: str | None = None
    last_error: str | None = None
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class TestSuiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class TestSuiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class TestSuiteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    description: str | None = None
    cases: list[TestCaseRead] = Field(default_factory=list)
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class TestCaseRunResult(BaseModel):
    case_id: UUID
    name: str
    status: TestCaseStatus
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


class TestSuiteRunResult(BaseModel):
    suite_id: UUID
    status: Literal["passed", "failed"]
    summary: str
    passed: int
    failed: int
    results: list[TestCaseRunResult] = Field(default_factory=list)
