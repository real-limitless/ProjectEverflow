"""Thin HTTP client for Everflow Platform API (sandbox token auth)."""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID

import httpx

# Short connect so unreachable guest URLs fail fast; read allows slower API work.
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)


class EverflowApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _resolve_timeout(timeout: httpx.Timeout | float | None) -> httpx.Timeout:
    if timeout is None:
        return DEFAULT_TIMEOUT
    if isinstance(timeout, httpx.Timeout):
        return timeout
    # Single float: apply to all phases (tests / callers).
    return httpx.Timeout(timeout)


class EverflowClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        project_id: str | None = None,
        timeout: httpx.Timeout | float | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("EVERFLOW_API_URL") or "").rstrip("/")
        self.token = token or os.environ.get("EVERFLOW_TOKEN") or ""
        self.project_id = project_id or os.environ.get("EVERFLOW_PROJECT_ID") or ""
        if not self.base_url:
            raise EverflowApiError("EVERFLOW_API_URL is required")
        if not self.token:
            raise EverflowApiError("EVERFLOW_TOKEN is required")
        if not self.project_id:
            raise EverflowApiError("EVERFLOW_PROJECT_ID is required")
        # Validate UUID shape early
        try:
            UUID(self.project_id)
        except ValueError as exc:
            raise EverflowApiError("EVERFLOW_PROJECT_ID must be a UUID") from exc
        self._timeout = _resolve_timeout(timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        expect_empty: bool = False,
    ) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                res = await client.request(
                    method,
                    self._url(path),
                    headers=self._headers(),
                    json=json_body,
                )
        except httpx.HTTPError as exc:
            # Connect/read timeouts often surface with empty str(exc).
            detail = str(exc).strip() or type(exc).__name__
            raise EverflowApiError(
                f"HTTP error talking to Everflow API: {detail} "
                f"(url={self.base_url!r}; guest MCP expects reverse tunnel on "
                f"127.0.0.1 — re-open Chat / opencode ensure if tunnel is down)"
            ) from exc

        if res.status_code >= 400:
            detail: Any
            try:
                detail = res.json()
            except Exception:  # noqa: BLE001
                detail = res.text
            raise EverflowApiError(
                f"Everflow API {method} {path} failed ({res.status_code}): {detail}",
                status_code=res.status_code,
                body=detail,
            )
        if expect_empty or res.status_code == 204 or not res.content:
            return None
        return res.json()

    # --- context ---

    async def whoami(self) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/projects/{self.project_id}/mcp/context")

    async def get_project(self) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/projects/{self.project_id}")

    async def list_projects(self) -> list[dict[str, Any]]:
        """v1: only the bound project (mutations stay project-scoped)."""
        proj = await self.get_project()
        return [proj] if isinstance(proj, dict) else []

    # --- knowledge ---

    async def list_canvases(self) -> list[dict[str, Any]]:
        data = await self.request("GET", f"/api/v1/projects/{self.project_id}/knowledge/canvases")
        return data if isinstance(data, list) else []

    async def get_canvas(self, canvas_id: str) -> dict[str, Any]:
        return await self.request(
            "GET",
            f"/api/v1/projects/{self.project_id}/knowledge/canvases/{canvas_id}",
        )

    async def create_canvas(
        self,
        *,
        name: str,
        description: str | None = None,
        content_md: str = "",
        origin: str = "created",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": name,
            "content_md": content_md,
            "origin": origin,
        }
        if description is not None:
            body["description"] = description
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/knowledge/canvases",
            json_body=body,
        )

    async def update_canvas(self, canvas_id: str, **fields: Any) -> dict[str, Any]:
        return await self.request(
            "PATCH",
            f"/api/v1/projects/{self.project_id}/knowledge/canvases/{canvas_id}",
            json_body={k: v for k, v in fields.items() if v is not None},
        )

    async def delete_canvas(self, canvas_id: str) -> None:
        await self.request(
            "DELETE",
            f"/api/v1/projects/{self.project_id}/knowledge/canvases/{canvas_id}",
            expect_empty=True,
        )

    async def reindex_canvas(self, canvas_id: str) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/knowledge/canvases/{canvas_id}/reindex",
        )

    async def knowledge_search(
        self,
        query: str,
        *,
        top_k: int = 5,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query, "top_k": top_k}
        if agent_id:
            body["agent_id"] = agent_id
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/knowledge/retrieve",
            json_body=body,
        )

    # --- agents ---

    async def list_agents(self) -> list[dict[str, Any]]:
        data = await self.request("GET", f"/api/v1/projects/{self.project_id}/agents")
        return data if isinstance(data, list) else []

    async def get_agent(self, agent_id: str) -> dict[str, Any]:
        return await self.request("GET", f"/api/v1/projects/{self.project_id}/agents/{agent_id}")

    async def create_agent(
        self,
        *,
        name: str,
        role: str = "general",
        description: str = "",
        system_prompt: str = "",
        tools: list[str] | None = None,
        active: bool = True,
    ) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/agents",
            json_body={
                "name": name,
                "role": role,
                "description": description,
                "system_prompt": system_prompt,
                "tools": tools or [],
                "active": active,
            },
        )

    async def update_agent(self, agent_id: str, **fields: Any) -> dict[str, Any]:
        return await self.request(
            "PATCH",
            f"/api/v1/projects/{self.project_id}/agents/{agent_id}",
            json_body={k: v for k, v in fields.items() if v is not None},
        )

    async def delete_agent(self, agent_id: str) -> None:
        await self.request(
            "DELETE",
            f"/api/v1/projects/{self.project_id}/agents/{agent_id}",
            expect_empty=True,
        )

    # --- tests ---

    async def list_test_suites(self) -> list[dict[str, Any]]:
        data = await self.request("GET", f"/api/v1/projects/{self.project_id}/tests/suites")
        return data if isinstance(data, list) else []

    async def create_test_suite(self, *, name: str, description: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/tests/suites",
            json_body=body,
        )

    async def create_test_case(
        self,
        suite_id: str,
        *,
        name: str,
        type: str = "unit",
        command: str = "",
    ) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/tests/suites/{suite_id}/cases",
            json_body={"name": name, "type": type, "command": command},
        )

    async def update_test_case(self, suite_id: str, case_id: str, **fields: Any) -> dict[str, Any]:
        return await self.request(
            "PATCH",
            f"/api/v1/projects/{self.project_id}/tests/suites/{suite_id}/cases/{case_id}",
            json_body={k: v for k, v in fields.items() if v is not None},
        )

    async def delete_test_case(self, suite_id: str, case_id: str) -> None:
        await self.request(
            "DELETE",
            f"/api/v1/projects/{self.project_id}/tests/suites/{suite_id}/cases/{case_id}",
            expect_empty=True,
        )

    async def run_test_suite(self, suite_id: str) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/tests/suites/{suite_id}/run",
        )

    # --- http tools ---

    async def list_http_tools(self) -> list[dict[str, Any]]:
        data = await self.request("GET", f"/api/v1/projects/{self.project_id}/http-tools")
        return data if isinstance(data, list) else []

    async def call_http_tool(
        self,
        tool_id: str,
        *,
        path_params: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        body: Any | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path_params": path_params or {},
            "query": query or {},
            "headers": headers or {},
        }
        if body is not None:
            payload["body"] = body
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/http-tools/{tool_id}/execute",
            json_body=payload,
        )

    # --- background jobs (detached sandbox processes) ---

    async def list_jobs(self) -> list[dict[str, Any]]:
        data = await self.request("GET", f"/api/v1/projects/{self.project_id}/jobs")
        return data if isinstance(data, list) else []

    async def create_job(
        self,
        *,
        title: str,
        command: str,
        cwd: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"title": title, "command": command}
        if cwd is not None:
            body["cwd"] = cwd
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/jobs",
            json_body=body,
        )

    async def get_job_logs(self, job_id: str, *, tail: int = 200) -> dict[str, Any]:
        return await self.request(
            "GET",
            f"/api/v1/projects/{self.project_id}/jobs/{job_id}/logs?tail={int(tail)}",
        )

    async def update_job(self, job_id: str, **fields: Any) -> dict[str, Any]:
        return await self.request(
            "PATCH",
            f"/api/v1/projects/{self.project_id}/jobs/{job_id}",
            json_body={k: v for k, v in fields.items() if v is not None},
        )

    async def start_job(self, job_id: str) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/jobs/{job_id}/start",
        )

    async def stop_job(self, job_id: str) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/jobs/{job_id}/stop",
        )

    async def kill_job(self, job_id: str) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/jobs/{job_id}/kill",
        )

    async def restart_job(self, job_id: str) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/jobs/{job_id}/restart",
        )

    async def delete_job(self, job_id: str) -> dict[str, Any]:
        return await self.request(
            "DELETE",
            f"/api/v1/projects/{self.project_id}/jobs/{job_id}",
        )


def dumps(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)
