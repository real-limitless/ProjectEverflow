# Release checklist (copy per cut)

Tag: `________________`  
Date: `________________`  
Branch: `Development-Everflow`

## Confirm with user

- [ ] Exact tag name
- [ ] Scope: docs+tag+notes (default) vs also GHCR
- [ ] Include uncommitted/untracked work? (default no)
- [ ] Update CORE README pointer? (default yes)
- [ ] Push/publish now or prepare only?

## Product branch files

- [ ] `VERSION` = tag
- [ ] `CHANGELOG.md` — new top section + install pins + limitations
- [ ] `docs/releases/<TAG>.md` — long-form notes
- [ ] `docs/releases/<TAG>-github.md` — GitHub Release body
- [ ] `README.md` — latest release row, clone pin, one-liner `EVERFLOW_VERSION`
- [ ] `ROADMAP.md` — Now/Next honesty
- [ ] `SECURITY.md` — supported versions table

## Commits & tag

- [ ] Product commit with `git commit -s`
- [ ] Annotated `git tag -a <TAG>`
- [ ] CORE commit with `git commit -s` (if pointer updated)
- [ ] Verified `git show <TAG>`

## Publish (user approval only)

- [ ] `git push origin Development-Everflow`
- [ ] `git push origin <TAG>`
- [ ] `git push origin CORE` (if updated)
- [ ] `gh release create …` or GitHub UI (pre-release for BETA/RC)

## Post-publish smoke

- [ ] Tag page loads on GitHub
- [ ] `git clone -b <TAG> …` works
- [ ] Install docs still say Compose-only
