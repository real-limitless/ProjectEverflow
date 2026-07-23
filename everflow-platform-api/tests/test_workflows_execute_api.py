"""HTTP tests for workflow execute + credentials."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient

FIXTURE = Path(__file__).parent / "fixtures" / "workflows" / "stock_agent_emailer.json"


async def _project(client: AsyncClient, headers: dict[str, str], slug: str = "exec-app") -> str:
    org = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "Exec Org", "slug": f"org-{slug}"},
    )
    assert org.status_code == 201, org.text
    proj = await client.post(
        f"/api/v1/orgs/{org.json()['id']}/projects",
        headers=headers,
        json={"name": "Exec", "slug": slug},
    )
    assert proj.status_code == 201, proj.text
    return proj.json()["id"]


@pytest.mark.asyncio
async def test_execute_stock_agent_via_api(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    project_id = await _project(client, auth_headers)
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))

    imp = await client.post(
        f"/api/v1/projects/{project_id}/workflows/import",
        headers=auth_headers,
        json=doc,
    )
    assert imp.status_code == 201, imp.text
    wf_id = imp.json()["id"]

    portfolio_csv = "Symbol,Qty,Cost\nAAPL,10,150.0,\n"
    history_csv = "Date,Symbol,Side\n2026-01-01,AAPL,BUY,\n"

    exe = await client.post(
        f"/api/v1/projects/{project_id}/workflows/{wf_id}/execute",
        headers=auth_headers,
        json={
            "trigger": "manual",
            # dry_run skips preflight credential gate (live execute requires bindings)
            "dry_run": True,
            "mocks": {
                "ftp_files": {
                    "/home/chen/Portfolio_Positions.csv": portfolio_csv,
                    "/home/chen/History_for_Account.csv": history_csv,
                },
                "capture_email": True,
                "agent_output": "# Report\n\nAll good.",
            },
        },
    )
    # ftp mock expects bytes — engine may need str->bytes; handle in test if fails
    assert exe.status_code == 201, exe.text
    body = exe.json()
    assert body["status"] in ("success", "error")
    if body["status"] != "success":
        # retry with note — str values in JSON become str; engine should encode
        pass
    assert body["status"] == "success", body.get("error_message") or body.get("log")
    assert body["log"]
    assert any(
        isinstance(x, dict) and x.get("node_name") == "Send Portfolio Research Email"
        for x in body["log"]
        if isinstance(x, dict)
    )


@pytest.mark.asyncio
async def test_credential_crud(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    project_id = await _project(client, auth_headers, slug="cred-app")
    created = await client.post(
        f"/api/v1/projects/{project_id}/workflow-credentials",
        headers=auth_headers,
        json={
            "credential_type": "smtp",
            "name": "SMTP account",
            "payload": {"host": "localhost", "port": 1025, "user": "u", "password": "p"},
        },
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    assert created.json()["credential_type"] == "smtp"
    # no secret in response
    assert "password" not in created.json()

    listed = await client.get(
        f"/api/v1/projects/{project_id}/workflow-credentials",
        headers=auth_headers,
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await client.delete(
        f"/api/v1/projects/{project_id}/workflow-credentials/{cid}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204
