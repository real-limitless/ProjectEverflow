# Real microVMs require the official microsandbox runtime (libkrunfw + msb).
# A plain python:slim + pip install is NOT enough — guest processes exit
# before startup without libkrunfw (unix_wait_status 256).
#
# Base: https://github.com/superradcompany/microsandbox (ghcr.io)
# Override for airgap after: ./deploy/local-registry.sh mirror-upstream
#   --build-arg MICRO_SANDBOX_BASE=localhost:5000/everflow/upstream-microsandbox:latest
ARG MICRO_SANDBOX_BASE=ghcr.io/superradcompany/microsandbox:latest
FROM ${MICRO_SANDBOX_BASE}

USER root
WORKDIR /app

# Official image is Ubuntu; ENTRYPOINT is `msb`. Override for our agent.
ENTRYPOINT []

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    ca-certificates \
    curl \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

# Avoid PEP 668 blocks for system Python in Ubuntu 24.04
ENV PIP_BREAK_SYSTEM_PACKAGES=1 \
    PYTHONUNBUFFERED=1

COPY everflow-sandbox-agent/pyproject.toml everflow-sandbox-agent/README.md ./
COPY everflow-sandbox-agent/app ./app
COPY everflow-mcp /opt/everflow-mcp

RUN pip3 install --no-cache-dir -e . \
    && pip3 install --no-cache-dir 'microsandbox' \
    && pip3 install --no-cache-dir /opt/everflow-mcp

# Real sandboxes only — do not default to mock in this image
ENV SANDBOX_MOCK=false \
    WORKSPACE_ROOT=/workspaces \
    HOST=0.0.0.0 \
    PORT=8090 \
    MSB_HOME=/root/.microsandbox

RUN mkdir -p /workspaces /root/.microsandbox \
    && msb doctor || true

EXPOSE 8090

# Verify KVM at start, then serve the control plane
CMD ["sh", "-c", "msb doctor; exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8090"]
