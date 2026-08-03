# Everflow control scripts

## Website one-liner — `get-everflow.sh`

Single remote bootstrap script for marketing sites / docs:

```bash
curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/Development-Everflow/scripts/get-everflow.sh | bash
```

Host the same file on your domain as e.g. `https://everflow.example/install` (raw file, `Content-Type: text/plain` or shell). The script clones the **product branch** (`Development-Everflow` by default; override with `EVERFLOW_VERSION`) into `~/everflow` (override with `EVERFLOW_DIR`) and runs the control tool.

See header comments in `get-everflow.sh` for all env vars.

## `./scripts/everflow` (recommended, after clone)

Terminal control plane for self-hosted Everflow: install, status, first admin, logs, upgrade, uninstall, reinstall.

```bash
# Interactive menu (TTY)
./scripts/everflow

# Interactive: ask → install registry → full stack
./scripts/everflow
# or: ./scripts/everflow install

# Non-interactive phased install
BUILD_FROM_SOURCE=1 ./scripts/everflow install          # seed from source, then stack
INSTALL_MODE=ghcr ./scripts/everflow install            # seed from GHCR, then stack
REGISTRY_SEED_MODE=skip ./scripts/everflow install      # registry already filled

# Registry only
./scripts/everflow registry up
./scripts/everflow registry seed build
./scripts/everflow registry status

# First platform admin (email + password + org)
./scripts/everflow setup-admin
# or non-interactive:
EVERFLOW_ADMIN_EMAIL=admin@example.com \
EVERFLOW_ADMIN_PASSWORD='choose-a-long-password' \
EVERFLOW_ORG_NAME='Acme' \
./scripts/everflow setup-admin

# Forgot admin password? Host-operator reset (no email flow yet):
./scripts/everflow reset-password
# or:
EVERFLOW_RESET_EMAIL=admin@example.com \
EVERFLOW_RESET_PASSWORD='new-long-password' \
./scripts/everflow reset-password

./scripts/everflow status
./scripts/everflow logs backend
./scripts/everflow upgrade                 # full: reseed registry + recreate stack
./scripts/everflow upgrade full build      # reseed from source, then stack
./scripts/everflow upgrade --stack-only    # recreate stack only (keep registry images)
./scripts/everflow uninstall            # containers only
./scripts/everflow uninstall --volumes  # wipe DB / sandboxes
./scripts/everflow reinstall --volumes
```

**Upgrade notes:** Interactive menu option **9** offers full (registry seed + stack) or stack-only. Full reseed uses `build` or `ghcr` (defaults from `REGISTRY_SEED_MODE` / `INSTALL_MODE` / `BUILD_FROM_SOURCE`, else GHCR). Data volumes and admin accounts are kept.

Host requirements: Docker or Podman + Compose. No host Python/Node for the control plane.

Layout:

| Path | Role |
|------|------|
| `everflow` | CLI entry + interactive menu |
| `lib/everflow-*.sh` | Shared helpers (stack, env, setup, TUI) |
| `everflow-install.sh` | Thin wrapper → `everflow install --no-admin` |
| `everflow-edge-install.sh` | Separate edge host sketch |

## First-run admin

Bootstrap uses the platform API (`POST /api/v1/setup/bootstrap`). Login is **email + password**. The browser UI wizard remains available if you skip CLI setup.

Never put the admin password in `.env` or the install log; use env vars or the interactive hidden prompt.
