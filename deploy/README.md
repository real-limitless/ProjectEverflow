# Deploy artifacts

| File | Purpose |
|------|---------|
| `sandbox-agent.Dockerfile` | **Host** control plane: microsandbox runtime + Everflow sandbox-agent API |
| `sandbox-guest.Dockerfile` | **Guest** microVM image for projects (Node + agent harnesses prebaked) |
| `build-sandbox-guest.sh` | Build/push the guest image |
| `backend.Dockerfile` / `frontend*.Dockerfile` | Platform API and UI |

## Guest image (fast project sandboxes)

```bash
# From repo root
./deploy/build-sandbox-guest.sh

# Custom tag / push
SANDBOX_GUEST_IMAGE=ghcr.io/limitless-rh/everflow-sandbox-guest:v1 PUSH=true ./deploy/build-sandbox-guest.sh
```

Then set:

```bash
SANDBOX_DEFAULT_IMAGE=ghcr.io/limitless-rh/everflow-sandbox-guest:dev
```

Microsandbox pulls OCI images into its cache (`MSB_HOME`). Use a tag the agent host can pull (local engine store when supported, or a registry). First provision may download once; later creates reuse the cache.

Upgrade harness versions by rebuilding the guest image (optional build-args: `CLAUDE_CODE_VERSION`, `OPENCODE_PACKAGE`).

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
