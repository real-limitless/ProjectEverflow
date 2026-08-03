# Security policy

## Supported versions

Security fixes target the **product branch** (`Development-Everflow`) and any published release tags. The **CORE** branch is documentation only.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for vulnerabilities that could put operators or tenants at risk.

1. Email the maintainers via the contact methods on the [GitHub organization](https://github.com/real-limitless) (or open a **private** security advisory on the repository if enabled).
2. Include: affected component, reproduction steps, impact, and whether a fix is known.
3. Allow reasonable time for a fix before public disclosure.

We will acknowledge reports as soon as practical and coordinate disclosure.

## Operator hygiene

- Never commit `.env`, API keys, private keys, or OAuth client secrets.
- In production set unique `SECRET_KEY`, `SANDBOX_AGENT_TOKEN`, and `CREDENTIALS_ENCRYPTION_KEY`.
- Keep `SANDBOX_MOCK=false` only on hosts with real KVM isolation you trust.
- Treat `sandbox-agent` as a privileged control plane: do not expose it to the public internet.
- Clients must talk only to the platform API — not directly to the sandbox agent.

## Scope notes

Everflow runs privileged containers and microVMs. Misconfiguration (default secrets, mock sandboxes in production, open agent ports) is an operator risk as much as a code risk. Reports that improve defaults, docs, or fail-closed checks are welcome.
