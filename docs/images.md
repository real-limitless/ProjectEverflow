# Everflow container images

Product runtime is **Docker Compose or Podman Compose** only. Control-plane
images are seeded into the embedded local registry (`localhost:5000/everflow/*`),
then Compose pulls those local refs.

`INSTALL_MODE=ghcr` **mirrors** published GHCR packages into that local registry.
It does **not** point Compose at GHCR directly, and it does **not** fall back to
a local compile if a pull fails.

## Required GHCR packages

Registry: `ghcr.io/real-limitless`

| Image | GHCR ref | Role |
|-------|----------|------|
| Frontend | `ghcr.io/real-limitless/everflow-frontend:<tag>` | UI (nginx; same-origin `/api`) |
| Backend | `ghcr.io/real-limitless/everflow-backend:<tag>` | Public platform API |
| Sandbox agent | `ghcr.io/real-limitless/everflow-sandbox-agent:<tag>` | Privileged microVM control plane (not a public client API) |
| Sandbox guest | `ghcr.io/real-limitless/everflow-sandbox-guest:<tag>` | Project microVM rootfs (msb pulls via `registry:5000/...`) |

Default `<tag>` is `latest` (`EVERFLOW_IMAGE_TAG`). Release tags (for example
`BETA-v0.0.1`) and `sha-<short>` are also applied by CI when the publish
workflow runs.

### Upstream images (not Everflow GHCR packages)

These are mirrored from other registries into the local registry during seed:

| Local name | Upstream source |
|------------|-----------------|
| `everflow/upstream-microsandbox` | `ghcr.io/superradcompany/microsandbox:latest` |
| `everflow/upstream-searxng` | `docker.io/searxng/searxng:latest` |
| `registry` compose service | `docker.io/library/registry:2` (host-cached bootstrap) |

## Tags

| Tag | When |
|-----|------|
| `latest` | Tip of `Development-Everflow` after a successful publish workflow |
| `BETA-vX.Y.Z` / `vX.Y.Z` | Git tag that triggered the workflow |
| `sha-<7>` | Git commit that built the image |
| `branch-development-everflow` | Branch slug from the workflow |

`BETA-v0.0.1` shipped **without** a guaranteed published multi-arch GHCR set.

### Publish status (after merge of #7)

Control-plane packages **are** on GHCR and linked to this repo (public,
`linux/amd64`, tags `latest` / `sha-446eb19` / `branch-Development-Everflow`):

- `ghcr.io/real-limitless/everflow-frontend`
- `ghcr.io/real-limitless/everflow-backend`
- `ghcr.io/real-limitless/everflow-sandbox-agent`

`everflow-sandbox-guest` already existed (public, tags `latest` + `dev` from
2026-07-21) but is **not linked** to `real-limitless/ProjectEverflow`.
`GITHUB_TOKEN` therefore gets `permission_denied: write_package` on push.
The guest **image builds** in CI; only the overwrite is blocked.

A maintainer must connect that package to this repository, then re-run
**Actions → Publish images**:

1. Open [everflow-sandbox-guest](https://github.com/users/real-limitless/packages/container/package/everflow-sandbox-guest).
2. **Package settings** → connect repository **ProjectEverflow**.
3. Re-run [Publish images](https://github.com/real-limitless/ProjectEverflow/actions/workflows/publish-images.yml).

Until that link exists, `INSTALL_MODE=ghcr` will fail honestly on the guest
image (use `BUILD_FROM_SOURCE=1` / `INSTALL_MODE=build`).

## How `INSTALL_MODE=ghcr` is supposed to work

```bash
INSTALL_MODE=ghcr EVERFLOW_IMAGE_TAG=latest ./scripts/everflow install
# or
./scripts/everflow install --mode=ghcr
```

1. Start the embedded `registry` service.
2. Mirror upstream microsandbox + SearXNG into `localhost:5000/everflow/`.
3. Pull the four Everflow images from `ghcr.io/real-limitless/*:<tag>` and push
   them into the local registry.
4. Rewrite `.env` image refs to `localhost:5000/everflow/*` (guest uses
   `registry:5000/everflow/everflow-sandbox-guest:<tag>`).
5. `compose up --no-build` from those local refs.

If step 3 cannot pull a required image, install **exits non-zero** and lists
the missing refs. It does **not** silently `compose --build`.

Reliable first install without published packages:

```bash
BUILD_FROM_SOURCE=1 ./scripts/everflow install
# equivalent
INSTALL_MODE=build ./scripts/everflow install
```

## Publishing (maintainers)

GitHub Actions: [`.github/workflows/publish-images.yml`](../.github/workflows/publish-images.yml)

- Triggers: push to `Development-Everflow`, version tags (`BETA-*`, `v*`),
  `workflow_dispatch`.
- Permissions: `packages: write` on `GITHUB_TOKEN`.
- Needs the GitHub org/repo to allow GHCR package creation for
  `ghcr.io/real-limitless/*`.

Manual:

```bash
docker login ghcr.io
EVERFLOW_REGISTRY=ghcr.io/real-limitless PUSH=true ./deploy/build-images.sh
EVERFLOW_IMAGE_TAG=BETA-v0.0.1 EVERFLOW_REGISTRY=ghcr.io/real-limitless PUSH=true ./deploy/build-images.sh
```

Primary architecture today is `linux/amd64` (KVM guests). Multi-arch sets are
not claimed until CI actually publishes them.

See also [`deploy/README.md`](../deploy/README.md).
