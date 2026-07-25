# Everflow project sandbox GUEST image (microVM root FS via microsandbox).
#
# Base: Fedora 44 (not the sandbox-agent host image — see sandbox-agent.Dockerfile).
# Tools baked here are available immediately after Sandbox.create — no dnf/npm
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

ARG BASE_IMAGE=fedora:44
# Official Node.js linux-x64 tarball major line (resolved at build via nodejs.org)
ARG NODE_MAJOR=22

FROM ${BASE_IMAGE}

ARG CLAUDE_CODE_VERSION=latest
# Primary package name; fallback tried in RUN if missing
ARG OPENCODE_PACKAGE=opencode-ai
# Official Playwright MCP + Chromium for opt-in OpenCode browser tools
ARG PLAYWRIGHT_MCP_VERSION=latest
ARG NODE_MAJOR=22
ARG NOVNC_VERSION=1.5.0

LABEL org.opencontainers.image.title="everflow-sandbox-guest" \
      org.opencontainers.image.description="Everflow project microVM image (Fedora) with Node + agent harnesses preinstalled" \
      everflow.prebaked="1" \
      everflow.guest.os="fedora" \
      everflow.guest.os.version="44"

ENV NPM_CONFIG_UPDATE_NOTIFIER=false \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/usr/local/bin:${PATH}" \
    PLAYWRIGHT_BROWSERS_PATH=/opt/everflow-browsers \
    # Avoid interactive dnf prompts in layers that shell out
    DNF_YUM_DISABLE_PLUGINS=""

# Core tools + desktop/noVNC stack + Playwright Chromium system libs.
# Selective XFCE packages (not full @xfce-desktop-environment) to limit image size.
# Playwright install-deps is apt-only; install Fedora equivalents manually.
RUN dnf -y --setopt=install_weak_deps=False upgrade \
    && dnf -y --setopt=install_weak_deps=False install \
        ca-certificates \
        curl \
        tar \
        xz \
        gzip \
        git \
        openssh-clients \
        bash \
        which \
        procps-ng \
        findutils \
        python3 \
        python3-pip \
        # noVNC webtop (HTTP + websockify on :6080)
        xorg-x11-server-Xvfb \
        xorg-x11-xauth \
        xrandr \
        dbus-x11 \
        dbus-daemon \
        xfce4-session \
        xfce4-settings \
        xfce4-terminal \
        xfce4-panel \
        xfwm4 \
        xfdesktop \
        Thunar \
        # Icons/themes: panel buttons + desktop background need these on Fedora.
        # Fedora 44 gdk-pixbuf loads PNG/SVG via glycin (bubblewrap sandbox), not
        # classic libpixbufloader-png — without glycin-loaders icons stay blank.
        adwaita-icon-theme \
        shared-mime-info \
        gdk-pixbuf2 \
        librsvg2 \
        glycin-loaders \
        bubblewrap \
        dejavu-sans-fonts \
        openbox \
        x11vnc \
        python3-websockify \
        # Playwright Chromium shared libraries (Fedora; no official install-deps)
        nss \
        nss-util \
        atk \
        at-spi2-atk \
        at-spi2-core \
        gtk3 \
        libdrm \
        libxkbcommon \
        libX11 \
        libXcomposite \
        libXdamage \
        libXext \
        libXfixes \
        libXrandr \
        libXcursor \
        libXi \
        libXtst \
        libxcb \
        mesa-libgbm \
        mesa-libGL \
        alsa-lib \
        cups-libs \
        pango \
        cairo \
        nspr \
        libxshmfence \
    && dnf clean all \
    && rm -rf /var/cache/dnf \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && ln -sf /usr/bin/pip3 /usr/local/bin/pip \
    # websockify CLI may be python3-websockify module only
    && if ! command -v websockify >/dev/null 2>&1; then \
         printf '%s\n' '#!/bin/sh' 'exec python3 -m websockify "$@"' \
           > /usr/local/bin/websockify && chmod +x /usr/local/bin/websockify; \
       fi \
    # MicroVMs have no systemd polkitd — remove the XFCE agent entirely so it
    # cannot autostart (Hidden=true stubs are not enough on all XFCE builds).
    && (dnf -y remove xfce-polkit 2>/dev/null || rpm -e --nodeps xfce-polkit 2>/dev/null || true) \
    && rm -f /usr/libexec/xfce-polkit \
    && mkdir -p /etc/xdg/autostart \
    && for _f in xfce-polkit.desktop openbox.desktop x11vnc.desktop; do \
         printf '%s\n' \
           '[Desktop Entry]' \
           'Type=Application' \
           'Name=disabled' \
           'Exec=/bin/true' \
           'Hidden=true' \
           'NoDisplay=true' \
           'X-GNOME-Autostart-enabled=false' \
           >"/etc/xdg/autostart/${_f}"; \
       done \
    # Ensure GTK can load Adwaita SVG icons in the guest
    && if command -v gdk-pixbuf-query-loaders-64 >/dev/null 2>&1; then \
         gdk-pixbuf-query-loaders-64 --update-cache; \
       elif command -v gdk-pixbuf-query-loaders >/dev/null 2>&1; then \
         gdk-pixbuf-query-loaders --update-cache; \
       fi \
    && update-mime-database /usr/share/mime 2>/dev/null || true

# noVNC from upstream tarball (avoid distro packages that pull nodejs)
RUN curl -fsSL "https://github.com/novnc/noVNC/archive/refs/tags/v${NOVNC_VERSION}.tar.gz" \
        | tar -xz -C /opt \
    && ln -sfn "/opt/noVNC-${NOVNC_VERSION}" /usr/share/novnc \
    && test -f /usr/share/novnc/vnc.html

# Node/npm: official linux-x64 tarball (glibc ABI matches modern Fedora; avoid
# multi-stage copy from Debian bookworm images).
RUN set -eux; \
    arch="$(uname -m)"; \
    case "$arch" in \
      x86_64) node_arch=x64 ;; \
      aarch64|arm64) node_arch=arm64 ;; \
      *) echo "unsupported arch: $arch" >&2; exit 1 ;; \
    esac; \
    # Resolve latest v${NODE_MAJOR}.x.y from nodejs.org index
    ver="$(curl -fsSL https://nodejs.org/dist/index.json \
      | python3 -c "import json,sys; maj=int('${NODE_MAJOR}'); \
v=next(x['version'] for x in json.load(sys.stdin) if x['version'].startswith(f'v{maj}.')); \
print(v.lstrip('v'))")"; \
    curl -fsSL "https://nodejs.org/dist/v${ver}/node-v${ver}-linux-${node_arch}.tar.xz" \
      | tar -xJ -C /usr/local --strip-components=1; \
    node -v && npm -v

# Agent harness CLIs (same packages as install_harnesses.sh)
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && (npm install -g "${OPENCODE_PACKAGE}" \
        || npm install -g @opencode-ai/cli \
        || npm install -g opencode-ai@latest) \
    && npm cache clean --force \
    && mkdir -p /etc/everflow /workspace \
    && printf 'prebaked=1\nos=fedora\nos_version=44\nnode=%s\nclaude=%s\nopencode=%s\n' \
        "$(node -v)" \
        "$(command -v claude 2>/dev/null || echo missing)" \
        "$(command -v opencode 2>/dev/null || echo missing)" \
        > /etc/everflow/prebaked \
    && test -x "$(command -v node)" \
    && cat /etc/everflow/prebaked

# Everflow MCP (stdio) — OpenCode registers this on ensure with project-scoped token.
# Use a dedicated venv so Fedora PEP 668 does not block system pip installs.
COPY everflow-mcp /opt/everflow-mcp
RUN python3 -m venv /opt/everflow-venv \
    && /opt/everflow-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/everflow-venv/bin/pip install --no-cache-dir /opt/everflow-mcp \
    && ln -sfn /opt/everflow-venv/bin/everflow-mcp /usr/local/bin/everflow-mcp \
    && everflow-mcp --version 2>/dev/null \
        || /opt/everflow-venv/bin/python -c "import everflow_mcp; print(everflow_mcp.__version__)" \
    && command -v everflow-mcp \
    && printf 'everflow_mcp=%s\n' "$(command -v everflow-mcp)" >> /etc/everflow/prebaked

# Playwright MCP + Chromium (opt-in via marketplace; headless default, headed on Desktop)
# System deps installed above via dnf; skip apt-only playwright install-deps.
RUN npm install -g "@playwright/mcp@${PLAYWRIGHT_MCP_VERSION}" \
    && mkdir -p /opt/everflow-browsers \
    && (cd /usr/local/lib/node_modules/@playwright/mcp \
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
