"""HTTP client for the internal sandbox-agent service."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings, get_settings


class SandboxAgentError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class SandboxAgentClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._settings.sandbox_agent_token}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        base = self._settings.sandbox_agent_url.rstrip("/")
        return f"{base}{path}"

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(self._url("/health"))
            res.raise_for_status()
            return res.json()

    async def create_sandbox(
        self,
        *,
        name: str,
        image: str,
        cpus: int,
        memory_mib: int,
        labels: dict[str, str],
        harnesses: list[str],
        workspace_host_path: str | None = None,
        replace: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "name": name,
            "image": image,
            "cpus": cpus,
            "memory_mib": memory_mib,
            "labels": labels,
            "harnesses": harnesses,
            "workspace_host_path": workspace_host_path,
            "replace": replace,
        }
        return await self._request("POST", "/v1/sandboxes", json=payload, expected=(201, 200))

    async def get_sandbox(self, name: str) -> dict[str, Any]:
        return await self._request("GET", f"/v1/sandboxes/{name}")

    async def start_sandbox(self, name: str) -> dict[str, Any]:
        return await self._request("POST", f"/v1/sandboxes/{name}/start")

    async def stop_sandbox(self, name: str) -> dict[str, Any]:
        return await self._request("POST", f"/v1/sandboxes/{name}/stop")

    async def remove_sandbox(self, name: str) -> None:
        await self._request("POST", f"/v1/sandboxes/{name}/remove", expected=(204, 404))

    async def exec(
        self,
        name: str,
        *,
        cmd: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_seconds: float | None = 120,
    ) -> dict[str, Any]:
        payload = {
            "cmd": cmd,
            "args": args or [],
            "cwd": cwd,
            "env": env or {},
            "timeout_seconds": timeout_seconds,
        }
        return await self._request("POST", f"/v1/sandboxes/{name}/exec", json=payload)

    async def bootstrap(self, name: str, harnesses: list[str]) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/v1/sandboxes/{name}/bootstrap",
            json={"harnesses": harnesses},
        )

    async def list_fs(self, name: str, path: str = ".") -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            f"/v1/sandboxes/{name}/fs",
            params={"path": path},
        )
        return list(data) if isinstance(data, list) else []

    async def read_fs(self, name: str, path: str) -> str:
        async with httpx.AsyncClient(timeout=self._settings.sandbox_agent_timeout_seconds) as client:
            res = await client.get(
                self._url(f"/v1/sandboxes/{name}/fs/content"),
                headers=self._headers(),
                params={"path": path},
            )
            if res.status_code >= 400:
                raise SandboxAgentError(
                    res.text or res.reason_phrase,
                    status_code=res.status_code,
                    body=res.text,
                )
            return res.text

    async def write_fs(self, name: str, path: str, content: str) -> None:
        await self._request(
            "PUT",
            f"/v1/sandboxes/{name}/fs/content",
            params={"path": path},
            json={"content": content},
            expected=(204,),
        )

    async def opencode_ensure(
        self,
        name: str,
        *,
        force_restart: bool = False,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/v1/sandboxes/{name}/opencode/ensure",
            json={"force_restart": force_restart},
        )

    async def opencode_proxy_stream(
        self,
        name: str,
        *,
        method: str,
        path: str,
        query: str | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> tuple[httpx.Response, httpx.AsyncClient]:
        """Open streaming response from agent OpenCode proxy.

        Caller must aclose both the response and the client.
        """
        rel = path.lstrip("/")
        url = self._url(
            f"/v1/sandboxes/{name}/opencode/{rel}" if rel else f"/v1/sandboxes/{name}/opencode"
        )
        if query:
            url = f"{url}?{query}"
        hdrs = self._headers()
        if headers:
            for k, v in headers.items():
                lk = k.lower()
                if lk in ("host", "content-length", "authorization"):
                    continue
                hdrs[k] = v
        timeout = httpx.Timeout(connect=10.0, read=None, write=60.0, pool=10.0)
        client = httpx.AsyncClient(timeout=timeout)
        try:
            req = client.build_request(method.upper(), url, headers=hdrs, content=content)
            res = await client.send(req, stream=True)
            return res, client
        except httpx.RequestError as exc:
            await client.aclose()
            raise SandboxAgentError(f"sandbox-agent unreachable: {exc}") from exc

    async def list_ports(self, name: str, *, probe: bool = False) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/v1/sandboxes/{name}/ports",
            params={"probe": "true" if probe else "false"},
        )

    async def preview_proxy_stream(
        self,
        name: str,
        *,
        port: int,
        method: str,
        path: str,
        query: str | None = None,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> tuple[httpx.Response, httpx.AsyncClient]:
        """Stream HTTP through agent port proxy. Caller must aclose response + client."""
        rel = path.lstrip("/")
        url = self._url(
            f"/v1/sandboxes/{name}/proxy/{port}/{rel}"
            if rel
            else f"/v1/sandboxes/{name}/proxy/{port}"
        )
        if query:
            url = f"{url}?{query}"
        hdrs = self._headers()
        if headers:
            for k, v in headers.items():
                lk = k.lower()
                if lk in ("host", "content-length", "authorization", "cookie"):
                    continue
                hdrs[k] = v
        timeout = httpx.Timeout(connect=10.0, read=None, write=60.0, pool=10.0)
        client = httpx.AsyncClient(timeout=timeout)
        try:
            req = client.build_request(method.upper(), url, headers=hdrs, content=content)
            res = await client.send(req, stream=True)
            return res, client
        except httpx.RequestError as exc:
            await client.aclose()
            raise SandboxAgentError(f"sandbox-agent unreachable: {exc}") from exc

    def preview_proxy_ws_url(
        self,
        name: str,
        *,
        port: int,
        path: str = "",
        query: str | None = None,
    ) -> str:
        base = self._settings.sandbox_agent_url.rstrip("/")
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://") :]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://") :]
        else:
            ws_base = base
        from urllib.parse import quote, urlencode

        rel = path.lstrip("/")
        # Encode path segments so Vite routes like @vite/client stay intact
        if rel:
            rel_enc = "/".join(quote(seg, safe="") for seg in rel.split("/"))
            path_part = f"/v1/sandboxes/{quote(name, safe='')}/proxy/{port}/{rel_enc}"
        else:
            path_part = f"/v1/sandboxes/{quote(name, safe='')}/proxy/{port}"
        q: dict[str, str] = {"token": self._settings.sandbox_agent_token}
        if query:
            # merge raw query pairs without token collision handled by agent
            from urllib.parse import parse_qsl

            for k, v in parse_qsl(query, keep_blank_values=True):
                if k != "token":
                    q[k] = v
        return f"{ws_base}{path_part}?{urlencode(q)}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        timeout = self._settings.sandbox_agent_timeout_seconds
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                res = await client.request(
                    method,
                    self._url(path),
                    headers=self._headers(),
                    json=json,
                    params=params,
                )
        except httpx.RequestError as exc:
            raise SandboxAgentError(f"sandbox-agent unreachable: {exc}") from exc

        if res.status_code not in expected:
            detail: Any
            try:
                detail = res.json()
            except Exception:  # noqa: BLE001
                detail = res.text
            msg = (
                detail.get("detail")
                if isinstance(detail, dict) and "detail" in detail
                else str(detail) or res.reason_phrase
            )
            raise SandboxAgentError(str(msg), status_code=res.status_code, body=detail)

        if res.status_code == 204 or not res.content:
            return None
        content_type = res.headers.get("content-type", "")
        if "application/json" in content_type:
            return res.json()
        return res.text
