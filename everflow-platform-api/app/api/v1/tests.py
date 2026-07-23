"""Project-scoped test suite / case CRUD and sandbox run."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.core.principal import Principal, get_principal, get_project_for_principal
from app.db.session import get_async_session
from app.models.project import Project
from app.models.test_suite import TestCase, TestSuite
from app.schemas.test_suite import (
    TestCaseCreate,
    TestCaseRead,
    TestCaseRunResult,
    TestCaseUpdate,
    TestSuiteCreate,
    TestSuiteRead,
    TestSuiteRunResult,
    TestSuiteUpdate,
)
from app.services.sandbox import MISSING_ON_AGENT, mark_sandbox_missing
from app.services.sandbox_agent_client import SandboxAgentClient, SandboxAgentError

router = APIRouter(tags=["tests"])


async def _get_suite_for_project(
    session: AsyncSession,
    project_id: UUID,
    suite_id: UUID,
    *,
    with_cases: bool = True,
) -> TestSuite:
    stmt = select(TestSuite).where(
        TestSuite.id == suite_id,
        TestSuite.project_id == project_id,
    )
    if with_cases:
        stmt = stmt.options(selectinload(TestSuite.cases))
    result = await session.execute(stmt)
    suite = result.scalar_one_or_none()
    if suite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test suite not found")
    return suite


async def _get_case_for_suite(
    session: AsyncSession,
    project_id: UUID,
    suite_id: UUID,
    case_id: UUID,
) -> TestCase:
    result = await session.execute(
        select(TestCase).where(
            TestCase.id == case_id,
            TestCase.suite_id == suite_id,
            TestCase.project_id == project_id,
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")
    return case


def _require_running_sandbox(project: Project) -> str:
    if not project.sandbox_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Project has no sandbox yet",
        )
    if project.sandbox_status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sandbox is not running (status={project.sandbox_status})",
        )
    return project.sandbox_name


@router.get(
    "/projects/{project_id}/tests/suites",
    response_model=list[TestSuiteRead],
)
async def list_suites(
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> list[TestSuite]:
    principal.require_scope("tests:read")
    result = await session.execute(
        select(TestSuite)
        .where(TestSuite.project_id == project.id)
        .options(selectinload(TestSuite.cases))
        .order_by(TestSuite.updated_at.desc())
    )
    return list(result.scalars().unique().all())


@router.post(
    "/projects/{project_id}/tests/suites",
    response_model=TestSuiteRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_suite(
    body: TestSuiteCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> TestSuite:
    principal.require_scope("tests:rw")
    suite = TestSuite(
        project_id=project.id,
        name=body.name.strip(),
        description=body.description,
        created_by=principal.user.id,
    )
    session.add(suite)
    await session.commit()
    return await _get_suite_for_project(session, project.id, suite.id)


@router.get(
    "/projects/{project_id}/tests/suites/{suite_id}",
    response_model=TestSuiteRead,
)
async def get_suite(
    suite_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> TestSuite:
    principal.require_scope("tests:read")
    return await _get_suite_for_project(session, project.id, suite_id)


@router.patch(
    "/projects/{project_id}/tests/suites/{suite_id}",
    response_model=TestSuiteRead,
)
async def update_suite(
    suite_id: UUID,
    body: TestSuiteUpdate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> TestSuite:
    principal.require_scope("tests:rw")
    suite = await _get_suite_for_project(session, project.id, suite_id)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        suite.name = data["name"].strip()
    if "description" in data:
        suite.description = data["description"]
    await session.commit()
    return await _get_suite_for_project(session, project.id, suite.id)


@router.delete(
    "/projects/{project_id}/tests/suites/{suite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_suite(
    suite_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("tests:rw")
    suite = await _get_suite_for_project(session, project.id, suite_id, with_cases=False)
    await session.delete(suite)
    await session.commit()


@router.post(
    "/projects/{project_id}/tests/suites/{suite_id}/cases",
    response_model=TestCaseRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_case(
    suite_id: UUID,
    body: TestCaseCreate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> TestCase:
    principal.require_scope("tests:rw")
    await _get_suite_for_project(session, project.id, suite_id, with_cases=False)
    case = TestCase(
        suite_id=suite_id,
        project_id=project.id,
        name=body.name.strip(),
        type=body.type,
        command=body.command,
        created_by=principal.user.id,
    )
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return case


@router.patch(
    "/projects/{project_id}/tests/suites/{suite_id}/cases/{case_id}",
    response_model=TestCaseRead,
)
async def update_case(
    suite_id: UUID,
    case_id: UUID,
    body: TestCaseUpdate,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> TestCase:
    principal.require_scope("tests:rw")
    case = await _get_case_for_suite(session, project.id, suite_id, case_id)
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        case.name = data["name"].strip()
    if "type" in data and data["type"] is not None:
        case.type = data["type"]
    if "command" in data and data["command"] is not None:
        case.command = data["command"]
    if "last_status" in data:
        case.last_status = data["last_status"]
    if "last_error" in data:
        case.last_error = data["last_error"]
    await session.commit()
    await session.refresh(case)
    return case


@router.delete(
    "/projects/{project_id}/tests/suites/{suite_id}/cases/{case_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_case(
    suite_id: UUID,
    case_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    principal.require_scope("tests:rw")
    case = await _get_case_for_suite(session, project.id, suite_id, case_id)
    await session.delete(case)
    await session.commit()


@router.post(
    "/projects/{project_id}/tests/suites/{suite_id}/run",
    response_model=TestSuiteRunResult,
)
async def run_suite(
    suite_id: UUID,
    project: Project = Depends(get_project_for_principal),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_async_session),
    settings: Settings = Depends(get_settings),
) -> TestSuiteRunResult:
    """Execute each case.command in the project sandbox via shell; update last_status."""
    principal.require_scope("tests:rw")
    suite = await _get_suite_for_project(session, project.id, suite_id)
    sandbox_name = _require_running_sandbox(project)
    client = SandboxAgentClient(settings)

    results: list[TestCaseRunResult] = []
    passed_n = 0
    failed_n = 0

    for case in suite.cases:
        cmd = (case.command or "").strip()
        if not cmd:
            case.last_status = "skipped"
            case.last_error = "Empty command"
            results.append(
                TestCaseRunResult(
                    case_id=case.id,
                    name=case.name,
                    status="skipped",
                    error="Empty command",
                )
            )
            continue

        try:
            raw = await client.exec(
                sandbox_name,
                cmd="sh",
                args=["-c", cmd],
                cwd="/workspace",
                timeout_seconds=120,
            )
        except SandboxAgentError as exc:
            if exc.status_code == 404:
                await mark_sandbox_missing(session, project)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=MISSING_ON_AGENT,
                ) from exc
            case.last_status = "failed"
            err = str(exc)[:2000]
            case.last_error = err
            failed_n += 1
            results.append(
                TestCaseRunResult(
                    case_id=case.id,
                    name=case.name,
                    status="failed",
                    error=err,
                )
            )
            continue

        exit_code = int(raw.get("exit_code", 1))
        stdout = str(raw.get("stdout", ""))
        stderr = str(raw.get("stderr", ""))
        if exit_code == 0:
            case.last_status = "passed"
            case.last_error = None
            passed_n += 1
            results.append(
                TestCaseRunResult(
                    case_id=case.id,
                    name=case.name,
                    status="passed",
                    exit_code=exit_code,
                    stdout=stdout[-4000:],
                    stderr=stderr[-4000:],
                )
            )
        else:
            case.last_status = "failed"
            err = (stderr or stdout or f"exit {exit_code}").strip()[:2000]
            case.last_error = err
            failed_n += 1
            results.append(
                TestCaseRunResult(
                    case_id=case.id,
                    name=case.name,
                    status="failed",
                    exit_code=exit_code,
                    stdout=stdout[-4000:],
                    stderr=stderr[-4000:],
                    error=err,
                )
            )

    await session.commit()

    overall: str = "failed" if failed_n else "passed"
    return TestSuiteRunResult(
        suite_id=suite.id,
        status=overall,  # type: ignore[arg-type]
        summary=f"{passed_n} passed · {failed_n} failed",
        passed=passed_n,
        failed=failed_n,
        results=results,
    )
