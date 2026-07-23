"""Preflight, validate-run, cancel, schedule parse, async execute."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.services.workflows.preflight import preflight_workflow
from app.services.workflows.scheduler import next_fire_utc, parse_schedule_hours

FIXTURE = Path(__file__).parent / "fixtures" / "workflows" / "stock_agent_emailer.json"


async def _project(client: AsyncClient, headers: dict[str, str], slug: str) -> str:
    org = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "P", "slug": f"org-{slug}"},
    )
    assert org.status_code == 201, org.text
    proj = await client.post(
        f"/api/v1/orgs/{org.json()['id']}/projects",
        headers=headers,
        json={"name": "P", "slug": slug},
    )
    assert proj.status_code == 201, proj.text
    return proj.json()["id"]


def test_parse_schedule_hours() -> None:
    doc = json.loads(FIXTURE.read_text())
    hours = parse_schedule_hours(doc)
    assert 9 in hours


def test_next_fire_utc() -> None:
    now = datetime(2026, 7, 21, 8, 0, tzinfo=timezone.utc)
    nxt = next_fire_utc([9], now)
    assert nxt is not None
    assert nxt.hour == 9


def test_preflight_missing_creds() -> None:
    doc = json.loads(FIXTURE.read_text())
    report = preflight_workflow(
        doc,
        credential_bindings={},
        available_credential_keys=set(),
        available_by_type=set(),
    )
    assert report["ok"] is False
    assert len(report["missing_credentials"]) >= 3


@pytest.mark.asyncio
async def test_validate_and_async_execute(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    project_id = await _project(client, auth_headers, "polish-1")
    doc = json.loads(FIXTURE.read_text())
    imp = await client.post(
        f"/api/v1/projects/{project_id}/workflows/import",
        headers=auth_headers,
        json=doc,
    )
    assert imp.status_code == 201, imp.text
    wf_id = imp.json()["id"]

    val = await client.post(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}/validate-run",
        headers=auth_headers,
    )
    assert val.status_code == 200, val.text
    assert val.json()["missing_credentials"]

    # dry-run background execute
    exe = await client.post(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}/execute",
        headers=auth_headers,
        json={
            "trigger": "manual",
            "dry_run": True,
            "background": False,
            "mocks": {
                "ftp_files": {
                    "/home/chen/Portfolio_Positions.csv": "Symbol,Qty\nAAPL,1,\n",
                    "/home/chen/History_for_Account.csv": "Date,Symbol\n2026-01-01,AAPL,\n",
                },
                "capture_email": True,
                "agent_output": "# ok",
            },
        },
    )
    assert exe.status_code == 201, exe.text
    assert exe.json()["status"] == "success"


@pytest.mark.asyncio
async def test_active_toggle_and_export(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    project_id = await _project(client, auth_headers, "polish-2")
    doc = json.loads(FIXTURE.read_text())
    imp = await client.post(
        f"/api/v1/projects/{project_id}/workflows/import",
        headers=auth_headers,
        json=doc,
    )
    wf_id = imp.json()["id"]
    patched = await client.patch(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}",
        headers=auth_headers,
        json={"active": True},
    )
    assert patched.status_code == 200
    assert patched.json()["active"] is True

    exported = await client.get(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}/export",
        headers=auth_headers,
    )
    assert exported.status_code == 200
    assert len(exported.json()["nodes"]) == 32


@pytest.mark.asyncio
async def test_bind_credentials(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project_id = await _project(client, auth_headers, "polish-3")
    created = await client.post(
        f"/api/v1/projects/{project_id}/workflow-credentials",
        headers=auth_headers,
        json={
            "credential_type": "smtp",
            "name": "SMTP account",
            "payload": {"host": "localhost", "port": 1025},
        },
    )
    assert created.status_code == 201
    cid = created.json()["id"]

    doc = json.loads(FIXTURE.read_text())
    imp = await client.post(
        f"/api/v1/projects/{project_id}/workflows/import",
        headers=auth_headers,
        json=doc,
    )
    wf_id = imp.json()["id"]
    bound = await client.patch(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}",
        headers=auth_headers,
        json={"credential_bindings": {"SMTP account": cid}},
    )
    assert bound.status_code == 200
    assert bound.json()["credential_bindings"]["SMTP account"] == cid
