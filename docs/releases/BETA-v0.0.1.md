# Release BETA-v0.0.1

**Status:** First public beta  
**Date:** 2026-08-03  
**Branch tip tagged:** `Development-Everflow`  
**License:** Apache-2.0  

> **Template for future cuts:** agents should follow `.grok/skills/release/SKILL.md` (`/release`) and copy this file / `CHANGELOG.md` structure for the next tag.

## What this is

A pin-able snapshot of the **runnable** Everflow control plane for early self-hosters and contributors. Install only via **Docker Compose or Podman Compose** (see product README).

## Get it

```bash
git clone -b BETA-v0.0.1 https://github.com/real-limitless/ProjectEverflow.git
cd ProjectEverflow
./scripts/everflow install
./scripts/everflow setup-admin
# UI → http://localhost:3000
```

One-liner (pinned):

```bash
EVERFLOW_VERSION=BETA-v0.0.1 \
  curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/BETA-v0.0.1/scripts/get-everflow.sh | bash
```

## Included

| Area | Notes |
|------|--------|
| Install | `./scripts/everflow`, local OCI registry seed, Compose stack |
| API | FastAPI platform API (auth, orgs, projects, sandbox proxy, …) |
| UI | PatternFly shell, playground workbench, marketplace, usage, harnesses catalog |
| Sandboxes | sandbox-agent + guest image path (KVM or mock for limited dev) |
| Governance | DCO, no CLA, code of conduct, security policy |

## Not guaranteed in this beta

- Fully published multi-arch GHCR image sets for zero-build install
- Production HA / multi-node edge maturity
- Stable public API or UI contracts (expect change)

## Feedback

- Issues / discussions on the GitHub repository  
- Security: [SECURITY.md](../../SECURITY.md)

Full changelog: [CHANGELOG.md](../../CHANGELOG.md).
