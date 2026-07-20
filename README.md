# Project Everflow

## Overview

Project Everflow is an enterprise-grade collaborative AI application development platform enabling teams to build, review, and deploy AI-powered applications with built-in safety, compliance, and approval workflows. It solves the problem of balancing rapid innovation with corporate governance by providing a "governance-first" environment where global compliance, regulatory, and data-handling rules are enforced at the platform level.

Inspired by creative platforms like HuggingFace Spaces, Everflow adds critical oversight to prevent unrestricted development. 
Users can freely create applications within pre-approved boundaries, ensuring consistency and inherent compliance for all tools.

Key features include:
- Visual workflow builders for AI applications
- Team collaboration and project forking
- AI-assisted project creation via chatbot, checked against corporate guidelines
- Multi-approver change request (PR) workflows with compliance checks
- Global sharing and deployment within the organization

Compared to contemporary tools like Continue, Lovable, v0.dev, or bolt.new, Everflow addresses the gap in managing organizational standards, avoiding "development drift" that leads to fragmented tooling and inconsistent methodologies.

In a typical use case, a support engineer can instantly develop an AI tool to analyze sosreports for system conditions, leveraging pre-configured compliant data access mechanisms (e.g., MCP servers), without triggering lengthy legal reviews.

## UI (PatternFly 6.6 React)

The interactive IDE-style frontend lives in **[`everflow-platform-ui/`](everflow-platform-ui/)**. It ports the [`playground-v2-pf.html`](playground-v2-pf.html) prototype to React + PatternFly 6.6.0 (vibe chat, dockable panels, workflows, deploy, etc. — mock data).

```bash
cd everflow-platform-ui
npm install
npm run dev
```

See [everflow-platform-ui/README.md](everflow-platform-ui/README.md) and [PLAN.md](PLAN.md) for architecture and roadmap.

## License

This project is licensed under the terms described in [LICENSE](LICENSE).


