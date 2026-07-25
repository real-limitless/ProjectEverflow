# Everflow project sandbox GUEST image (microVM root FS via microsandbox).
#
# This is NOT the sandbox-agent host image (see sandbox-agent.Dockerfile).
# Tools baked here are available immediately after Sandbox.create — no apt/npm
# install on the create path.
#
# Build:
#   ./deploy/build-sandbox-guest.sh
#   # or:
#   docker build -f deploy/sandbox-guest.Dockerfile -t everflow-sandbox-guest:dev .
#
# Use:
#   SANDBOX_DEFAULT_IMAGE=everflow-sandbox-guest:dev
#   # or a registry ref microsandbox can pull, e.g. ghcr.io/org/everflow-sandbox-guest:latest

# syntax=docker/dockerfile:1

ARG NODE_IMAGE=node:22-bookworm-slim
ARG BASE_IMAGE=python:3.12-slim-bookworm

FROM ${NODE_IMAGE} AS nodebase

FROM ${BASE_IMAGE}

ARG CLAUDE_CODE_VERSION=latest
# Primary package name; fallback tried in RUN if missing
ARG OPENCODE_PACKAGE=opencode-ai
# Official Playwright MCP + Chromium for opt-in OpenCode browser tools
ARG PLAYWRIGHT_MCP_VERSION=latest

LABEL org.opencontainers.image.title="everflow-sandbox-guest" \
      org.opencontainers.image.description="Everflow project microVM image with Node + agent harnesses preinstalled" \
      everflow.prebaked="1"

ENV DEBIAN_FRONTEND=noninteractive \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/usr/local/bin:${PATH}" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/everflow-browsers

ARG NOVNC_VERSION=1.5.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        openssh-client \
        bash \
        procps \
        # noVNC webtop (HTTP + websockify on :6080); avoid apt novnc (pulls nodejs)
        xvfb \
        dbus-x11 \
        xfce4 \
        xfce4-terminal \
        xfce4-session \
        xfwm4 \
        xfdesktop4 \
        xfce4-panel \
        thunar \
        fonts-dejavu-core \
        openbox \
        x11vnc \
        websockify \
    && curl -fsSL "https://github.com/novnc/noVNC/archive/refs/tags/v${NOVNC_VERSION}.tar.gz" \
        | tar -xz -C /opt \
    && ln -sfn "/opt/noVNC-${NOVNC_VERSION}" /usr/share/novnc \
    && test -f /usr/share/novnc/vnc.html \
    && rm -rf /var/lib/apt/lists/*

# Node/npm from official image (reliable PATH under /usr/local)
COPY --from=nodebase /usr/local/bin/node /usr/local/bin/node
COPY --from=nodebase /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && node -v && npm -v

# Agent harness CLIs (same packages as install_harnesses.sh)
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && (npm install -g "${OPENCODE_PACKAGE}" \
        || npm install -g @opencode-ai/cli \
        || npm install -g opencode-ai@latest) \
    && npm cache clean --force \
    && mkdir -p /etc/everflow /workspace \
    && printf 'prebaked=1\nnode=%s\nclaude=%s\nopencode=%s\n' \
        "$(node -v)" \
        "$(command -v claude 2>/dev/null || echo missing)" \
        "$(command -v opencode 2>/dev/null || echo missing)" \
        > /etc/everflow/prebaked \
    && test -x "$(command -v node)" \
    && cat /etc/everflow/prebaked

# Everflow MCP (stdio) — OpenCode registers this on ensure with project-scoped token
COPY everflow-mcp /opt/everflow-mcp
RUN pip install --no-cache-dir /opt/everflow-mcp \
    && everflow-mcp --version 2>/dev/null || python -c "import everflow_mcp; print(everflow_mcp.__version__)" \
    && command -v everflow-mcp \
    && printf 'everflow_mcp=%s\n' "$(command -v everflow-mcp)" >> /etc/everflow/prebaked

# Playwright MCP + Chromium (opt-in via marketplace; headless default, headed on Desktop)
# Image grows significantly; avoids cold npx + browser download on first Chat use.
RUN npm install -g "@playwright/mcp@${PLAYWRIGHT_MCP_VERSION}" \
    && mkdir -p /opt/everflow-browsers \
    && (cd /usr/local/lib/node_modules/@playwright/mcp \
        && npx --yes playwright install-deps chromium \
        && PLAYWRIGHT_BROWSERS_PATH=/opt/everflow-browsers npx --yes playwright install chromium) \
    && npm cache clean --force \
    && printf 'playwright_mcp=%s\nbrowsers=%s\n' \
        "$(command -v playwright-mcp 2>/dev/null || ls /usr/local/lib/node_modules/@playwright/mcp/cli.js 2>/dev/null || echo missing)" \
        "/opt/everflow-browsers" \
        >> /etc/everflow/prebaked

# Desktop / noVNC stack (started by entrypoint; disable with EF_DESKTOP_ENABLE=0)
COPY deploy/sandbox-guest-desktop.sh /usr/local/bin/everflow-desktop.sh
COPY deploy/sandbox-guest-entrypoint.sh /usr/local/bin/sandbox-guest-entrypoint.sh
COPY deploy/everflow-playwright-mcp.sh /usr/local/bin/everflow-playwright-mcp
RUN chmod +x /usr/local/bin/everflow-desktop.sh \
        /usr/local/bin/sandbox-guest-entrypoint.sh \
        /usr/local/bin/everflow-playwright-mcp \
    && printf 'novnc=6080\nplaywright_wrapper=/usr/local/bin/everflow-playwright-mcp\n' \
        >> /etc/everflow/prebaked

WORKDIR /workspace

# Microsandbox supplies the guest process model; keep a harmless default.
ENTRYPOINT ["/usr/local/bin/sandbox-guest-entrypoint.sh"]
CMD ["sleep", "infinity"]
