# Changelog

All notable releases of **Project Everflow** are documented here.

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
Version tags use the project scheme `BETA-vX.Y.Z` for early public betas.

---

## [BETA-v0.0.1] — 2026-08-03

First **public beta** of the runnable product branch (`Development-Everflow`).

### Highlights

- **Compose-only product runtime** — Docker Compose or Podman Compose is the only supported way to run the full stack (frontend, backend, sandbox-agent, registry, searxng).
- **Self-host install TUI** — `./scripts/everflow` (install, registry seed, status, setup-admin, logs, upgrade, uninstall).
- **One-liner bootstrap** — `scripts/get-everflow.sh` (pin with `EVERFLOW_VERSION=BETA-v0.0.1`).
- **Platform API** — auth, orgs, projects, providers, knowledge, marketplace, sandbox proxy, git, harness pack.
- **Platform UI** — PatternFly workbench, marketplace, usage, harness catalog page.
- **Isolated project sandboxes** — microsandbox microVMs via privileged sandbox-agent.
- **Open source governance** — Apache-2.0, DCO (no CLA), Contributor Covenant, security policy.

### Install (pinned release)

```bash
git clone -b BETA-v0.0.1 https://github.com/real-limitless/ProjectEverflow.git
cd ProjectEverflow
./scripts/everflow install
./scripts/everflow setup-admin
```

Or:

```bash
EVERFLOW_VERSION=BETA-v0.0.1 EVERFLOW_NONINTERACTIVE=1 \
  curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/BETA-v0.0.1/scripts/get-everflow.sh | bash
```

### Known limitations (beta)

- Pre-built **GHCR** images for every platform arch may not be fully published; prefer `BUILD_FROM_SOURCE=1` / local registry seed for a reliable first install.
- Overview and some surfaces remain thin; workflows integrations are maturing.
- Production operators should set unique secrets, real KVM (`SANDBOX_MOCK=false`), and review [SECURITY.md](SECURITY.md).
- This is **beta** software — expect breaking changes before a stable `v1.0.0`.

### Upgrade path

Track `Development-Everflow` for ongoing work, or wait for a later tag. Re-run `./scripts/everflow upgrade` after checking out a newer ref.

[BETA-v0.0.1]: https://github.com/real-limitless/ProjectEverflow/releases/tag/BETA-v0.0.1
