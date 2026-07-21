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
SANDBOX_GUEST_IMAGE=ghcr.io/myorg/everflow-sandbox-guest:v1 PUSH=true ./deploy/build-sandbox-guest.sh
```

Then set:

```bash
SANDBOX_DEFAULT_IMAGE=everflow-sandbox-guest:dev
```

Microsandbox pulls OCI images into its cache (`MSB_HOME`). Use a tag the agent host can pull (local engine store when supported, or a registry). First provision may download once; later creates reuse the cache.

Upgrade harness versions by rebuilding the guest image (optional build-args: `CLAUDE_CODE_VERSION`, `OPENCODE_PACKAGE`).
