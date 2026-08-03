# Security policy

## Supported versions

| Ref | Support |
|-----|---------|
| **`Development-Everflow`** | Active development; security fixes land here first |
| **`BETA-v0.0.1`** and later release tags | Best-effort fixes; prefer upgrading to a newer tag or the product branch |
| **`CORE`** | Documentation only — no runtime |

The **CORE** branch is methodology only and does not ship the product stack.

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
