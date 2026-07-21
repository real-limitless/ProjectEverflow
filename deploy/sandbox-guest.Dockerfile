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

LABEL org.opencontainers.image.title="everflow-sandbox-guest" \
      org.opencontainers.image.description="Everflow project microVM image with Node + agent harnesses preinstalled" \
      everflow.prebaked="1"

ENV DEBIAN_FRONTEND=noninteractive \
    NPM_CONFIG_UPDATE_NOTIFIER=false \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/usr/local/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        bash \
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

WORKDIR /workspace

# Microsandbox supplies the guest process model; keep a harmless default.
CMD ["sleep", "infinity"]
