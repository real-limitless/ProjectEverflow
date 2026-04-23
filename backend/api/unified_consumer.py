"""
Unified Agent WebSocket Consumer — the single entry point for all
agent/chat interactions from the frontend.

Replaces the old ``LangGraphStreamConsumer`` and the SSE ``stream()`` endpoint.
All chat modes (ask, plan, agent, persona, deep) flow through here.

Protocol
--------
Client → Server  (JSON):

    {
      "type": "message",
      "content": "...",
      "context_files": [{"path": "...", "content": "..."}],
    }

    { "type": "cancel" }

Server → Client  (JSON):

    { "type": "connected", ... }
    { "type": "text_chunk", "content": "...", "node": "..." }
    { "type": "tool_start", "name": "...", "args": {...} }
    { "type": "tool_result", "name": "...", "output": "...", "duration": 1.2 }
    { "type": "worker_start", "worker": "coder" }
    { "type": "worker_end", "worker": "coder", "content": "..." }
    { "type": "todos_update", "todos": [...] }
    { "type": "complete", "content": "...", "tool_calls": [...], "elapsed_seconds": 3.4 }
    { "type": "error", "message": "..." }
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import traceback

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.utils import timezone

from api.models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)


class UnifiedAgentConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for all agent modes."""

    # ── Connection lifecycle ────────────────────────────────────────

    async def connect(self):
        self.project_id = self.scope["url_route"]["kwargs"]["project_id"]
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.user = self.scope.get("user")
        self._agent_task: asyncio.Task | None = None

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        try:
            session = await sync_to_async(
                ChatSession.objects.select_related("project", "persona").get
            )(pk=self.session_id, user=self.user)

            if session.project_id != int(self.project_id):
                await self.close(code=4003)
                return

            if not await self._check_access(self.user, session.project):
                await self.close(code=4003)
                return

            self.session = session
            self.group_name = f"agent_session_{self.session_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()

            await self._send_event({
                "type": "connected",
                "session_id": int(self.session_id),
                "mode": session.mode,
                "user": self.user.username,
            })

        except ChatSession.DoesNotExist:
            await self.close(code=4004)
        except Exception as exc:
            logger.error("Agent WS connect error: %s", exc, exc_info=True)
            await self.close(code=4000)

    async def disconnect(self, close_code):
        # Cancel running agent task
        if self._agent_task and not self._agent_task.done():
            self._agent_task.cancel()
            try:
                await self._agent_task
            except (asyncio.CancelledError, Exception):
                pass

        if hasattr(self, "group_name"):
            try:
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
            except Exception:
                pass

    # ── Receive from client ─────────────────────────────────────────

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self._send_event({"type": "error", "message": "Invalid JSON"})
            return

        msg_type = data.get("type", "message")

        if msg_type == "cancel":
            if self._agent_task and not self._agent_task.done():
                self._agent_task.cancel()
                await self._send_event({"type": "error", "message": "Cancelled by user"})
            return

        if msg_type == "message":
            content = (data.get("content") or "").strip()
            if not content:
                return

            # If an agent is already running, reject
            if self._agent_task and not self._agent_task.done():
                await self._send_event({"type": "error", "message": "Agent is already running. Send 'cancel' first."})
                return

            context_files = data.get("context_files", [])
            self._agent_task = asyncio.create_task(
                self._run_agent(content, context_files)
            )

    # ── Channel layer handler (for group broadcasts) ────────────────

    async def agent_event(self, event):
        """Forward events from channel layer to the WS client."""
        payload = event.get("payload", event)
        await self._send_event(payload)

    # ── Agent execution ─────────────────────────────────────────────

    async def _run_agent(self, user_input: str, context_files: list):
        """Create graph, stream events, persist messages."""
        start = time.monotonic()

        # Reload session to pick up any mode/tool changes
        self.session = await sync_to_async(
            ChatSession.objects.select_related("project", "persona").get
        )(pk=self.session_id)

        # Persist user message
        await sync_to_async(ChatMessage.objects.create)(
            session=self.session,
            message_type="user",
            content=user_input,
        )

        try:
            # Lazy import to avoid circular deps and defer heavy loads
            from api.frameworks.langgraph.graph import create_agent_graph
            from api.frameworks.langgraph.streaming import stream_agent_events

            graph = await sync_to_async(create_agent_graph)(
                self.session,
                container_name=f"proj-pod-{self.session.project_id}-workspace-shared",
                mode=self.session.mode,
            )

            final_content = ""
            final_tool_calls = []

            async for event in stream_agent_events(
                graph,
                user_input,
                self.session,
                context_files=context_files,
            ):
                await self._send_event(event)

                # Capture final response
                if event.get("type") == "complete":
                    final_content = event.get("content", "")
                    final_tool_calls = event.get("tool_calls", [])

            # Persist assistant message
            if final_content:
                msg = await sync_to_async(ChatMessage.objects.create)(
                    session=self.session,
                    message_type="assistant",
                    content=final_content,
                )

                # Store tool calls as metadata
                if final_tool_calls:
                    msg.metadata = {"tool_calls": final_tool_calls}
                    await sync_to_async(msg.save)()

            # Update session timestamp + iteration count
            await sync_to_async(self._update_session_stats)()

        except asyncio.CancelledError:
            logger.info("Agent cancelled for session %s", self.session_id)
            raise
        except Exception as exc:
            logger.error("Agent error session=%s: %s", self.session_id, exc, exc_info=True)
            await self._send_event({
                "type": "error",
                "message": f"Agent failed: {str(exc)}",
            })

    def _update_session_stats(self):
        """Sync helper to bump iteration count."""
        self.session.agent_iterations += 1
        self.session.save(update_fields=["agent_iterations", "updated_at"])

    # ── Helpers ─────────────────────────────────────────────────────

    async def _send_event(self, payload: dict):
        try:
            await self.send(text_data=json.dumps(payload, default=str))
        except Exception as exc:
            logger.warning("Failed to send WS event: %s", exc)

    async def _check_access(self, user, project):
        if project.owner_id == user.id:
            return True
        is_contributor = await sync_to_async(
            lambda: project.contributors.filter(id=user.id).exists()
        )()
        if is_contributor:
            return True
        if project.team_id:
            is_team_member = await sync_to_async(
                lambda: project.team.members.filter(id=user.id).exists()
            )()
            if is_team_member:
                return True
        return False
