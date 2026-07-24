"""Thin HTTP client for Everflow Platform API (sandbox token auth)."""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID

import httpx


class EverflowApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class EverflowClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        project_id: str | None = None,
        timeout: float = 60.0,
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
        self._timeout = timeout

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

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        expect_empty: bool = False,
    ) -> Any:
        try:
            with httpx.Client(timeout=self._timeout) as client:
                res = client.request(
                    method,
                    self._url(path),
                    headers=self._headers(),
                    json=json_body,
                )
        except httpx.HTTPError as exc:
            raise EverflowApiError(f"HTTP error talking to Everflow API: {exc}") from exc

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

    def whoami(self) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/projects/{self.project_id}/mcp/context")

    def get_project(self) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/projects/{self.project_id}")

    def list_projects(self) -> list[dict[str, Any]]:
        """v1: only the bound project (mutations stay project-scoped)."""
        proj = self.get_project()
        return [proj] if isinstance(proj, dict) else []

    # --- knowledge ---

    def list_canvases(self) -> list[dict[str, Any]]:
        data = self.request("GET", f"/api/v1/projects/{self.project_id}/knowledge/canvases")
        return data if isinstance(data, list) else []

    def get_canvas(self, canvas_id: str) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/api/v1/projects/{self.project_id}/knowledge/canvases/{canvas_id}",
        )

    def create_canvas(
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
        return self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/knowledge/canvases",
            json_body=body,
        )

    def update_canvas(self, canvas_id: str, **fields: Any) -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/api/v1/projects/{self.project_id}/knowledge/canvases/{canvas_id}",
            json_body={k: v for k, v in fields.items() if v is not None},
        )

    def delete_canvas(self, canvas_id: str) -> None:
        self.request(
            "DELETE",
            f"/api/v1/projects/{self.project_id}/knowledge/canvases/{canvas_id}",
            expect_empty=True,
        )

    def reindex_canvas(self, canvas_id: str) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/knowledge/canvases/{canvas_id}/reindex",
        )

    def knowledge_search(
        self,
        query: str,
        *,
        top_k: int = 5,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query, "top_k": top_k}
        if agent_id:
            body["agent_id"] = agent_id
        return self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/knowledge/retrieve",
            json_body=body,
        )

    # --- agents ---

    def list_agents(self) -> list[dict[str, Any]]:
        data = self.request("GET", f"/api/v1/projects/{self.project_id}/agents")
        return data if isinstance(data, list) else []

    def get_agent(self, agent_id: str) -> dict[str, Any]:
        return self.request("GET", f"/api/v1/projects/{self.project_id}/agents/{agent_id}")

    def create_agent(
        self,
        *,
        name: str,
        role: str = "general",
        description: str = "",
        system_prompt: str = "",
        tools: list[str] | None = None,
        active: bool = True,
    ) -> dict[str, Any]:
        return self.request(
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

    def update_agent(self, agent_id: str, **fields: Any) -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/api/v1/projects/{self.project_id}/agents/{agent_id}",
            json_body={k: v for k, v in fields.items() if v is not None},
        )

    def delete_agent(self, agent_id: str) -> None:
        self.request(
            "DELETE",
            f"/api/v1/projects/{self.project_id}/agents/{agent_id}",
            expect_empty=True,
        )

    # --- tests ---

    def list_test_suites(self) -> list[dict[str, Any]]:
        data = self.request("GET", f"/api/v1/projects/{self.project_id}/tests/suites")
        return data if isinstance(data, list) else []

    def create_test_suite(self, *, name: str, description: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name}
        if description is not None:
            body["description"] = description
        return self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/tests/suites",
            json_body=body,
        )

    def create_test_case(
        self,
        suite_id: str,
        *,
        name: str,
        type: str = "unit",
        command: str = "",
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/tests/suites/{suite_id}/cases",
            json_body={"name": name, "type": type, "command": command},
        )

    def update_test_case(self, suite_id: str, case_id: str, **fields: Any) -> dict[str, Any]:
        return self.request(
            "PATCH",
            f"/api/v1/projects/{self.project_id}/tests/suites/{suite_id}/cases/{case_id}",
            json_body={k: v for k, v in fields.items() if v is not None},
        )

    def delete_test_case(self, suite_id: str, case_id: str) -> None:
        self.request(
            "DELETE",
            f"/api/v1/projects/{self.project_id}/tests/suites/{suite_id}/cases/{case_id}",
            expect_empty=True,
        )

    def run_test_suite(self, suite_id: str) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/tests/suites/{suite_id}/run",
        )

    # --- http tools ---

    def list_http_tools(self) -> list[dict[str, Any]]:
        data = self.request("GET", f"/api/v1/projects/{self.project_id}/http-tools")
        return data if isinstance(data, list) else []

    def call_http_tool(
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
        return self.request(
            "POST",
            f"/api/v1/projects/{self.project_id}/http-tools/{tool_id}/execute",
            json_body=payload,
        )


def dumps(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)
