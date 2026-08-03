---
name: release
description: >
  Cut a Project Everflow public release the same way as BETA-v0.0.1: VERSION,
  CHANGELOG, docs/releases notes, README/ROADMAP/SECURITY pins, CORE pointer,
  DCO-signed commit, annotated git tag, optional GitHub Release body. Use when
  the user asks for a release, beta/rc tag, "ship a version", "cut BETA-v…",
  "public release", "tag a release", or runs /release.
metadata:
  short-description: "Cut Everflow public releases (BETA-vX.Y.Z)"
---

# Release — Project Everflow

Reproduce the **BETA-v0.0.1** release process for every future public tag.

## When to use

User wants a **public** product release (beta, rc, or stable). Not for private experiment branches.

## Hard rules

1. **Product tags** live on **`Development-Everflow`** (runnable monorepo). Never tag product releases on `CORE` alone.
2. **Supported runtime stays Compose-only** (Docker Compose / Podman Compose). Do not reintroduce host multi-process install as supported.
3. **DCO required** — every release prep commit uses `git commit -s`. No CLA.
4. **Do not push** branch, tag, or create GitHub Release until the user explicitly asks.
5. **Do not force-push** or move an already-published tag without explicit user approval.
6. Prefer **not** bundling unrelated untracked files (e.g. ad-hoc screenshots) unless the user opts in.
7. After code changes on the product branch, keep docs honest about beta limitations and GHCR availability.

## Version naming

| Phase | Tag scheme | GitHub Release |
|-------|------------|----------------|
| Early public beta | `BETA-vX.Y.Z` (e.g. `BETA-v0.0.2`) | Mark **pre-release** |
| Release candidate | `RC-vX.Y.Z` or `vX.Y.Z-rc.N` | Pre-release |
| Stable | `vX.Y.Z` | Full release |

- Read current `VERSION` and latest `CHANGELOG.md` section before choosing the next tag.
- Ask the user if the next version number is ambiguous; recommend the next logical tag.
- Tag string **must** match `VERSION` file contents (single line, no trailing junk).

## Preconditions checklist

Run before editing:

```bash
git rev-parse --abbrev-ref HEAD   # expect Development-Everflow
git status -sb
git log origin/Development-Everflow..HEAD --oneline
git tag -l 'BETA-*' 'v*' 'RC-*' | sort -V | tail -20
cat VERSION 2>/dev/null || true
head -40 CHANGELOG.md
```

Confirm with the user (if not already answered):

1. **Exact tag name** (e.g. `BETA-v0.0.2`)
2. **Scope:**
   - **Default:** docs + git tag + GitHub release notes draft (no GHCR build)
   - Optional: also publish GHCR images (long, needs registry login — only if asked)
3. **Include uncommitted/untracked work?** Default **no** unless they say yes.
4. **CORE pointer update?** Default **yes** (install pin on CORE README).

## Release workflow (do in order)

### 1. Product branch prep (`Development-Everflow`)

Set `TAG` to the release id (e.g. `BETA-v0.0.2`). Use today’s date from user_info when writing changelogs.

#### 1a. `VERSION`

Write exactly:

```text
<TAG>
```

#### 1b. `CHANGELOG.md`

- Keep [Keep a Changelog](https://keepachangelog.com/)-style sections.
- **Prepend** a new `## [<TAG>] — YYYY-MM-DD` section (never delete old sections).
- Include: Highlights, Install (pinned), Known limitations, Upgrade path.
- Install snippets must use the new tag:

```bash
git clone -b <TAG> https://github.com/real-limitless/ProjectEverflow.git
cd ProjectEverflow
./scripts/everflow install
./scripts/everflow setup-admin
```

```bash
EVERFLOW_VERSION=<TAG> EVERFLOW_NONINTERACTIVE=1 \
  curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/<TAG>/scripts/get-everflow.sh | bash
```

- Footer link: `[<TAG>]: https://github.com/real-limitless/ProjectEverflow/releases/tag/<TAG>`

#### 1c. `docs/releases/<TAG>.md`

Long-form notes (model after `docs/releases/BETA-v0.0.1.md`):

- Status, date, branch tip, license
- What this is
- Get it (clone + one-liner)
- Included table
- Not guaranteed / known limitations
- Feedback + link to CHANGELOG

#### 1d. `docs/releases/<TAG>-github.md`

Short body for `gh release create --notes-file` (model after `BETA-v0.0.1-github.md`):

- Title-style intro
- Install blocks
- What’s in / limitations
- Links to CHANGELOG and long-form notes

This file may be committed with the release prep commit **or** left untracked for publish-only use; prefer **committing** it so the tag tree is self-contained.

#### 1e. `README.md`

Update:

- Table row **Latest public beta** / **Latest release** → link to the new tag + CHANGELOG
- Quick start: **pinned** clone uses new tag; keep Development-Everflow as “latest tip”
- One-liner table/examples: `EVERFLOW_VERSION=<TAG>` and raw URL under `/<TAG>/scripts/get-everflow.sh`

#### 1f. `ROADMAP.md`

- Move or add the release under **Now (usable)** (e.g. public beta/rc/stable tag)
- Keep honest **Next** items (GHCR, operator docs, hardening, …)

#### 1g. `SECURITY.md`

- Supported versions table: product branch active; list this tag (and prior tags as best-effort); CORE = docs only

### 2. CORE branch pointer

CORE is concept-only. Still update install pointers so the default GitHub branch stays accurate:

1. Open CORE worktree (create if needed):

```bash
git fetch origin CORE
git worktree add /tmp/everflow-core-release CORE   # or reuse existing CORE worktree
```

2. Edit CORE `README.md` **Get the software** / Quick install:
   - Pinned public release: `git clone -b <TAG> …`
   - Latest tip: `Development-Everflow`
3. Commit on CORE with DCO (`git commit -s`). Do **not** put product source trees on CORE.

### 3. Commit on product branch (DCO)

Stage only release artifacts (not unrelated untracked noise):

```bash
git add VERSION CHANGELOG.md docs/releases/<TAG>.md docs/releases/<TAG>-github.md \
  README.md ROADMAP.md SECURITY.md
git commit -s -m "$(cat <<EOF
release: prepare public release <TAG>

Add VERSION, CHANGELOG, release notes, and install pin docs for <TAG>.
Compose-only install remains the supported product runtime.
EOF
)"
```

### 4. Annotated tag

Create the tag on the release prep commit:

```bash
git tag -a <TAG> -m "$(cat <<EOF
Project Everflow <TAG>

Public release of the runnable product stack.

Install:
  git clone -b <TAG> https://github.com/real-limitless/ProjectEverflow.git
  cd ProjectEverflow && ./scripts/everflow install

See CHANGELOG.md and docs/releases/<TAG>.md
EOF
)"
```

Verify:

```bash
git rev-parse <TAG>^{commit}
git show <TAG> --stat --no-patch
```

### 5. Stop for publish approval

Report local state:

- Product commit SHA and tag
- CORE commit(s) if any
- Unpushed commits vs `origin/*`
- That **nothing is public** until push

**Only if the user asks to publish**, run (or give them) something equivalent to:

```bash
# Product
git push origin Development-Everflow
git push origin <TAG>

# CORE
git -C <core-worktree> push origin CORE

# GitHub Release (optional; pre-release for BETA/RC)
gh release create <TAG> \
  --title "<TAG> — …" \
  --notes-file docs/releases/<TAG>-github.md \
  --prerelease    # omit --prerelease for stable vX.Y.Z
```

If `gh` is missing, provide UI steps: GitHub → Releases → Draft from tag → paste notes → pre-release checkbox for betas.

### 6. Optional GHCR (only when user requests)

Not part of the default BETA-v0.0.1-style cut:

- `EVERFLOW_IMAGE_TAG=<TAG> EVERFLOW_REGISTRY=ghcr.io/real-limitless PUSH=true ./deploy/build-images.sh`
- Document in CHANGELOG whether GHCR install path is ready
- Requires credentials and long builds — confirm first

## What not to do

- Do not tag from a dirty tree of unrelated WIP without user consent
- Do not rewrite history of published tags
- Do not claim GHCR zero-build install if images were not published
- Do not skip CORE pointer when the default branch is CORE (users land there first)
- Do not use CLA bots or drop DCO for release commits

## Reference copies of BETA-v0.0.1

Use these as templates (adjust tag and notes):

| Artifact | Path |
|----------|------|
| Version file | `VERSION` |
| Changelog | `CHANGELOG.md` |
| Long notes | `docs/releases/BETA-v0.0.1.md` |
| GitHub body | `docs/releases/BETA-v0.0.1-github.md` |
| Compact checklist | `.grok/skills/release/references/checklist.md` |

## After a successful public release

- Confirm tag URL: `https://github.com/real-limitless/ProjectEverflow/releases/tag/<TAG>`
- Confirm clone `-b <TAG>` works
- Optionally remind maintainers: branch protection + required DCO check still on
- Leave uncommitted screenshots / local tooling alone unless asked

## Agent communication

When finished preparing (before push), summarize:

1. Tag name and commit SHA  
2. Files touched  
3. CORE update status  
4. Exact publish commands waiting for approval  
