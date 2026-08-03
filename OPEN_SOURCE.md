# Open source participation practices

Project Everflow follows community practices aligned with
[Red Hat’s Open Source Participation Guidelines](https://www.redhat.com/en/resources/open-source-participation-guidelines-overview)
(especially §7.1 for project maintainers handling community contributions).
Those guidelines describe how Red Hat associates participate in open source;
this document records how **this repository** implements the same spirit for
contributors and maintainers.

This is a community project under the Apache License 2.0. It is not a formal
Red Hat product policy document.

## Principles we follow

| Principle | How we practice it here |
|-----------|-------------------------|
| **Default to open** | Source, docs, and install tooling live in a public git repository under an OSI-approved license. |
| **Open source license** | [Apache License 2.0](LICENSE) for project code and documentation unless a file says otherwise. |
| **No CLA / no assignment** | We do **not** require contributor license agreements or copyright assignment. Contributions are accepted under the project license (inbound = outbound). |
| **Developer Certificate of Origin (DCO)** | Every commit in a PR must include a `Signed-off-by` line certifying the [DCO 1.1](DCO). See [CONTRIBUTING.md](CONTRIBUTING.md). |
| **Upstream-first mindset** | Prefer fixing and improving this public tree over long-lived private forks of Everflow itself. |
| **Code of conduct** | [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) (Contributor Covenant). |
| **Security honesty** | Private vulnerability reporting via [SECURITY.md](SECURITY.md). |
| **Compose-native product** | Supported runtime is Docker Compose or Podman Compose only — see [README.md](README.md). |

## What we do **not** do

- Require a CLA, CCLA, or copyright assignment for community contributions
- Accept proprietary or “source available but not open source” licenses for core project code
- Document host multi-process installs as a supported product path (Compose only)

## Enforcement (mechanical)

| Control | Mechanism |
|---------|-----------|
| DCO sign-off | CI workflow [`.github/workflows/dco.yml`](.github/workflows/dco.yml) fails PRs without valid `Signed-off-by` |
| PR checklist | [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) |
| License | Root `LICENSE` (Apache-2.0) |
| Conduct | Moderators enforce [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) |

**Maintainer recommendation:** On GitHub, mark the **DCO** check as a required status check on `Development-Everflow` (Settings → Branches → Branch protection rules). Automation alone is not enough if the check can be skipped.

## How to certify a contribution (DCO)

```bash
git commit -s -m "feat: short description"
# or amend: git commit --amend -s
```

The `-s` flag adds:

```text
Signed-off-by: Your Name <you@example.com>
```

Use your real name and a contact email you control. The full legal text is in [DCO](DCO) and at [developercertificate.org](https://developercertificate.org/).

## License compliance notes

- Prefer well-known OSI-approved licenses for new dependencies.
- Do not introduce non-open-source dependencies into the product stack without an explicit maintainer review and documentation.
- Keep third-party notices intact; do not strip license headers from vendored material.

## References

- [Red Hat Open Source Participation Guidelines (overview)](https://www.redhat.com/en/resources/open-source-participation-guidelines-overview)
- [Developer Certificate of Origin](https://developercertificate.org/)
- [Open Source Definition (OSI)](https://opensource.org/osd)
- [Contributor Covenant](https://www.contributor-covenant.org/)
