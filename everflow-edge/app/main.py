"""Everflow edge agent — lightweight FastAPI skeleton for deploy hosts.

MVP endpoints:
  GET /health     — liveness for Traefik / install checks
  POST /heartbeat — stub registration/heartbeat for the platform (Issue 15)

Full node registration, mTLS, and workload orchestration come later.
"""

from __future__ import annotations

import os
import socket
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(
    title="everflow-edge",
    version="0.1.0",
    description="Edge agent on deploy hosts (Traefik + docker compose)",
)

NODE_ID = os.environ.get("EVERFLOW_EDGE_NODE_ID") or socket.gethostname()
TAGS = [t.strip() for t in os.environ.get("EVERFLOW_EDGE_TAGS", "docker").split(",") if t.strip()]


class HeartbeatBody(BaseModel):
    """Optional payload from platform; ignored for now beyond echo."""

    platform_url: str | None = None
    token: str | None = Field(default=None, description="Future node registration JWT")


class HeartbeatResponse(BaseModel):
    status: str = "ok"
    node_id: str
    hostname: str
    tags: list[str]
    ts: str
    note: str = "stub — platform registration not yet wired"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "everflow-edge", "node_id": NODE_ID}


@app.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(body: HeartbeatBody | None = None) -> HeartbeatResponse:
    _ = body  # reserved for future platform URL / token exchange
    return HeartbeatResponse(
        node_id=NODE_ID,
        hostname=socket.gethostname(),
        tags=TAGS,
        ts=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "everflow-edge",
        "node_id": NODE_ID,
        "docs": "/docs",
        "health": "/health",
        "heartbeat": "POST /heartbeat",
    }


def run() -> None:
    import uvicorn

    host = os.environ.get("EVERFLOW_EDGE_HOST", "0.0.0.0")
    port = int(os.environ.get("EVERFLOW_EDGE_PORT", "9100"))
    uvicorn.run("app.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run()
