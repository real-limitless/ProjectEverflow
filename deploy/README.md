# Deploy artifacts

| File | Purpose |
|------|---------|
| `local-registry.sh` | **Embedded registry** lifecycle: up, seed, mirror, export/import |
| `build-images.sh` | Build/push **all** Everflow images (frontend, backend, sandbox-agent, guest) |
| `build-sandbox-guest.sh` | Thin wrapper: guest image only (`ONLY=guest`) |
| `sandbox-agent.Dockerfile` | **Host** control plane: microsandbox runtime + Everflow sandbox-agent API |
| `sandbox-guest.Dockerfile` | **Guest** microVM image for projects (Node + agent harnesses prebaked) |
| `backend.Dockerfile` / `frontend*.Dockerfile` | Platform API and UI |

## Embedded local registry (product default)

Compose always runs a private Distribution registry (`registry:2`) on
`127.0.0.1:5000` (host) / `registry:5000` (compose network).

| Who pulls | Image host in the ref |
|-----------|------------------------|
| Host Docker/Podman (`compose image:`) | `localhost:5000/everflow/...` |
| microsandbox inside `sandbox-agent` | `registry:5000/everflow/...` |

Same repository path after one push — no dual-push required.

### First-time seed (online)

```bash
# Mirror upstream (microsandbox, searxng) + build/push all Everflow images
./deploy/local-registry.sh seed

# Or mirror published GHCR images without a local compile:
SEED_FROM_GHCR=1 ./deploy/local-registry.sh seed
# equivalent: ./deploy/local-registry.sh mirror-upstream && ./deploy/local-registry.sh mirror-ghcr
```

### HTTP / insecure registry

Local registry speaks plain HTTP. Two layers need insecure access:

| Who | Hostname | Config |
|-----|----------|--------|
| Host Docker/Podman (compose `image:`, seed push) | `localhost:5000` | Podman registries.conf / Docker `insecure-registries` |
| microsandbox inside `sandbox-agent` (guest pull) | `registry:5000` | Agent seeds `$MSB_HOME/config.json` `registries.hosts.*.insecure` |

**Seed/install auto-configures Podman** by writing:

`~/.config/containers/registries.conf.d/everflow-local-registry.conf`

and uses `podman push --tls-verify=false` for local tags. No manual Podman setup is required.

**Docker Engine** (not podman-docker) still needs a one-time daemon change:

```json
{
  "insecure-registries": ["localhost:5000", "127.0.0.1:5000"]
}
```

Then `sudo systemctl restart docker`.

**msb (guest microVM image):** if provision fails with `https://registry:5000/... registry error`,
the agent should already mark that host insecure on startup. Ensure the guest
image exists (`./deploy/local-registry.sh status` / `ONLY=guest … build-push`)
and restart `sandbox-agent`. Manual: `msb pull --insecure registry:5000/everflow/everflow-sandbox-guest:latest`.

### Airgap export / import

On an online builder:

```bash
./deploy/local-registry.sh seed
./deploy/local-registry.sh export /media/usb/everflow-images.tar
```

On the offline host (engine must already have `registry:2` or load it from the tarball):

```bash
./deploy/local-registry.sh import /media/usb/everflow-images.tar
./scripts/everflow install
```

### Commands

```bash
./deploy/local-registry.sh up
./deploy/local-registry.sh status
./deploy/local-registry.sh mirror-upstream
./deploy/local-registry.sh build-push          # ONLY=guest for guest only
./deploy/local-registry.sh mirror-ghcr
./deploy/local-registry.sh env-snippet
```

## Build images (maintainers)

From repo root:

```bash
# Local registry tags (default): localhost:5000/everflow/*:latest
./deploy/build-images.sh
PUSH=true ./deploy/build-images.sh

# Publish to GHCR
docker login ghcr.io
EVERFLOW_REGISTRY=ghcr.io/limitless-rh PUSH=true ./deploy/build-images.sh

# Versioned release
EVERFLOW_IMAGE_TAG=v0.1.0 EVERFLOW_REGISTRY=ghcr.io/limitless-rh PUSH=true ./deploy/build-images.sh

# Subset
ONLY=backend,frontend ./deploy/build-images.sh
ONLY=guest ./deploy/build-images.sh

# Podman
CONTAINER_ENGINE=podman ./deploy/build-images.sh
```

| Image | Local ref (host) | msb / internal ref |
|-------|------------------|--------------------|
| Frontend | `localhost:5000/everflow/everflow-frontend:latest` | — |
| Backend | `localhost:5000/everflow/everflow-backend:latest` | — |
| Sandbox agent | `localhost:5000/everflow/everflow-sandbox-agent:latest` | — |
| Sandbox guest | `localhost:5000/everflow/everflow-sandbox-guest:latest` | `registry:5000/everflow/everflow-sandbox-guest:latest` |
| Upstream microsandbox | `localhost:5000/everflow/upstream-microsandbox:latest` | agent Dockerfile `MICRO_SANDBOX_BASE` |
| Upstream searxng | `localhost:5000/everflow/upstream-searxng:latest` | compose `searxng` |

Frontend is built with **empty** `VITE_API_URL` so the UI uses same-origin `/api` (nginx → backend).

After seeding, install with:

```bash
./scripts/everflow install
```

## Guest image only (legacy wrapper)

```bash
./deploy/build-sandbox-guest.sh
ONLY=guest PUSH=true ./deploy/local-registry.sh build-push
```

Microsandbox pulls OCI images into its cache (`MSB_HOME`). First provision may download once from the **local** registry; later creates reuse the cache.

Upgrade harness versions by rebuilding the guest image (optional build-args on the Dockerfile: `CLAUDE_CODE_VERSION`, `OPENCODE_PACKAGE`, `PLAYWRIGHT_MCP_VERSION`).

The guest image prebakes **Chromium + `@playwright/mcp`** and the `everflow-playwright-mcp` wrapper (`PLAYWRIGHT_BROWSERS_PATH=/opt/everflow-browsers`). Marketplace **Browser (Playwright)** is opt-in for OpenCode; headless is default, headed uses the Desktop/noVNC stack. Rebuild the guest after changing browser tooling.

## Live Preview (wildcard subdomains)

The playground Preview panel loads user apps via:

```text
{scheme}://{endpoint_id}.{PREVIEW_BASE_DOMAIN}/
```

Each listening sandbox port gets a stable UUIDv4 `endpoint_id`. Auth is a short-lived ticket (query → HttpOnly cookie). The platform API terminates Host-based routing and proxies HTTP/WebSocket to the sandbox-agent.

### Local / Compose defaults

| Variable | Default | Meaning |
|----------|---------|---------|
| `PREVIEW_ENABLED` | `true` | Master switch |
| `PREVIEW_BASE_DOMAIN` | `preview.localhost:8000` | Hostname suffix (may include `:port`) |
| `PREVIEW_PUBLIC_SCHEME` | `http` | `http` or `https` |
| `PREVIEW_TICKET_TTL_SECONDS` | `1200` | Ticket/cookie lifetime |

Browsers resolve `*.localhost` to `127.0.0.1`, so iframe URLs like  
`http://<uuid>.preview.localhost:8000/` hit the API on port 8000.

### Production

1. DNS: `*.preview.example.com` → preview edge (platform API or dedicated edge).
2. TLS: wildcard cert for `*.preview.example.com`.
3. Set:

```bash
PREVIEW_BASE_DOMAIN=preview.example.com
PREVIEW_PUBLIC_SCHEME=https
```

4. Edge must forward `Host`, `Upgrade`, and `Connection` for WebSocket HMR (see `frontend-nginx.conf` Upgrade headers for a pattern).

**Do not** set main app session cookies with `Domain=.example.com` if that would also attach to `*.preview.example.com`. Keep app cookies host-only or on a separate app host.
