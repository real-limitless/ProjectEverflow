"""Minimal fake OpenCode HTTP server for unit tests (not production)."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse


class _Handler(BaseHTTPRequestHandler):
    sessions: dict[str, dict[str, Any]] = {}
    messages: dict[str, list[dict[str, Any]]] = {}
    providers_connected: list[str] = []

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _json(self, code: int, body: Any) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/global/health":
            self._json(200, {"healthy": True, "version": "fake-0.0.1"})
            return
        if path == "/session":
            self._json(200, list(self.sessions.values()))
            return
        if path == "/provider":
            self._json(
                200,
                {
                    "all": [
                        {"id": "openrouter", "name": "OpenRouter"},
                        {"id": "openai", "name": "OpenAI"},
                        {"id": "anthropic", "name": "Anthropic"},
                        {"id": "xai", "name": "xAI"},
                    ],
                    "default": {},
                    "connected": list(self.providers_connected),
                },
            )
            return
        if path == "/config/providers":
            self._json(
                200,
                {
                    "providers": [
                        {
                            "id": "openrouter",
                            "name": "OpenRouter",
                            "models": {
                                "openrouter/auto": {
                                    "id": "openrouter/auto",
                                    "name": "OpenRouter Auto",
                                }
                            },
                        },
                        {
                            "id": "openai",
                            "name": "OpenAI",
                            "models": {"gpt-4.1": {"id": "gpt-4.1", "name": "GPT-4.1"}},
                        },
                        {
                            "id": "anthropic",
                            "name": "Anthropic",
                            "models": {
                                "claude-sonnet-4": {
                                    "id": "claude-sonnet-4",
                                    "name": "Claude Sonnet",
                                }
                            },
                        },
                        {
                            "id": "xai",
                            "name": "xAI",
                            "models": {"grok-2": {"id": "grok-2", "name": "Grok 2"}},
                        },
                    ],
                    "default": {},
                },
            )
            return
        if path == "/mcp":
            self._json(200, {})
            return
        if path == "/agent":
            self._json(
                200,
                [
                    {"name": "build", "mode": "primary"},
                    {"name": "plan", "mode": "primary"},
                ],
            )
            return
        if path == "/command":
            self._json(200, [{"name": "init", "description": "Initialize"}])
            return
        if path == "/event":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(b"data: {\"type\":\"server.connected\"}\n\n")
            self.wfile.flush()
            return
        if path.startswith("/session/") and path.endswith("/message"):
            sid = path.split("/")[2]
            self._json(200, self.messages.get(sid, []))
            return
        if path.startswith("/session/"):
            sid = path.split("/")[2]
            sess = self.sessions.get(sid)
            if not sess:
                self._json(404, {"error": "not found"})
                return
            self._json(200, sess)
            return
        self._json(404, {"error": f"unknown {path}"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        body = self._read_json() or {}
        if path == "/session":
            import uuid

            # Prefer real OpenCode id shape so UI filters (ses_…) accept fake sessions.
            sid = f"ses_{uuid.uuid4().hex[:24]}"
            sess = {
                "id": sid,
                "title": body.get("title") or "New session",
                "time": {"created": 0, "updated": 0},
            }
            self.sessions[sid] = sess
            self.messages[sid] = []
            self._json(200, sess)
            return
        # POST /session/:id/permissions/:permissionID
        if "/permissions/" in path and path.startswith("/session/"):
            self._json(200, True)
            return
        # POST /permission/:id/reply (alternate)
        if path.startswith("/permission/") and path.endswith("/reply"):
            self._json(200, True)
            return
        if path.startswith("/session/") and path.endswith("/prompt_async"):
            sid = path.split("/")[2]
            parts = body.get("parts") or []
            text = ""
            for p in parts:
                if isinstance(p, dict) and p.get("type") == "text":
                    text = str(p.get("text") or "")
            agent = str(body.get("agent") or "")
            tools = body.get("tools") if isinstance(body.get("tools"), dict) else {}
            user_msg = {
                "info": {"id": f"u-{len(self.messages.get(sid, []))}", "role": "user"},
                "parts": [{"type": "text", "text": text}],
            }
            asst_parts: list[dict[str, Any]] = [
                {"type": "reasoning", "text": "Thinking…"},
                {
                    "type": "text",
                    "text": f"Echo: {text}"
                    + (f" (agent={agent})" if agent else "")
                    + (f" tools={tools}" if tools else ""),
                },
            ]
            # Simulate a permission request when edit tools are not denied
            if tools.get("edit") is not False and tools.get("bash") is not False:
                asst_parts.append(
                    {
                        "type": "permission",
                        "permissionID": f"perm-{sid[:8]}",
                        "permission": "bash",
                        "title": "bash",
                        "patterns": ["ls *"],
                    }
                )
            asst = {
                "info": {
                    "id": f"a-{len(self.messages.get(sid, []))}",
                    "role": "assistant",
                    "agent": agent or None,
                },
                "parts": asst_parts,
            }
            self.messages.setdefault(sid, []).extend([user_msg, asst])
            self.send_response(204)
            self.end_headers()
            return
        if path.startswith("/session/") and path.endswith("/message"):
            sid = path.split("/")[2]
            parts = body.get("parts") or []
            text = ""
            for p in parts:
                if isinstance(p, dict) and p.get("type") == "text":
                    text = str(p.get("text") or "")
            asst = {
                "info": {"id": "a-sync", "role": "assistant"},
                "parts": [{"type": "text", "text": f"Echo: {text}"}],
            }
            self.messages.setdefault(sid, []).append(
                {
                    "info": {"id": "u-sync", "role": "user"},
                    "parts": [{"type": "text", "text": text}],
                }
            )
            self.messages[sid].append(asst)
            self._json(200, asst)
            return
        self._json(404, {"error": f"unknown POST {path}"})

    def do_PUT(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/auth/"):
            pid = path.split("/")[2]
            if pid not in self.providers_connected:
                self.providers_connected.append(pid)
            self._json(200, True)
            return
        self._json(404, {"error": f"unknown PUT {path}"})

    def do_PATCH(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        body = self._read_json() or {}
        if path.startswith("/session/"):
            sid = path.split("/")[2]
            sess = self.sessions.get(sid)
            if not sess:
                self._json(404, {"error": "not found"})
                return
            if "title" in body:
                sess["title"] = body["title"]
            self._json(200, sess)
            return
        self._json(404, {"error": f"unknown PATCH {path}"})

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/session/"):
            sid = path.split("/")[2]
            self.sessions.pop(sid, None)
            self.messages.pop(sid, None)
            self._json(200, True)
            return
        self._json(404, {"error": f"unknown DELETE {path}"})


def start_fake_opencode(port: int = 0) -> tuple[ThreadingHTTPServer, int, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    chosen = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, chosen, thread
