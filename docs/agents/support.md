## Support & Documentation

- **Main Docs**: README.md
- **Agent Docs**: AGENTS.md (this file)
- **API Docs**: (To be added)
- **Component Library**: Storybook (planned)

---

## Glossary

**Project & Collaboration**:
- **PR**: Pull Request / Change Request
- **CR**: Change Request (same as PR)
- **Owner**: Project creator with full permissions
- **Contributor**: Team member actively working on project
- **Approval**: Positive review of a change request
- **Merge**: Integrating approved changes into main codebase

**Compliance & Security**:
- **AI Prompt**: Instructions for AI to validate code/compliance
- **Template**: Group of compliance checks
- **Check**: Individual compliance validation rule
- **RLS**: Row Level Security (database access control)

**Workspace & Containers**:
- **Pod**: Podman pod - isolated namespace containing multiple containers for a project
- **Service**: Container running within a pod (e.g., webtop, workspace, backend)
- **Webtop**: Full Linux desktop environment accessible via browser (Fedora KDE)
- **Workspace**: AI development container with project files and tools
- **Volume**: Persistent storage for workspace files and configuration
- **Resource Tier**: T-shirt sizing for container resources (CPU, memory limits)
- **Orchestrator**: Abstraction layer for container management (Podman, K8s)
- **Proxy**: Authenticated backend proxy for accessing workspace services

**AI & Chat**:
- **Persona**: AI assistant personality/role with specific behavior
- **Chat Mode**: Interaction style (ask, plan, agent, persona)
- **LLM**: Large Language Model (GPT-4, Claude, etc.)
- **Temperature**: AI creativity parameter (0.0 = deterministic, 2.0 = creative)
- **Max Tokens**: Maximum length of AI response
- **System Prompt**: Instructions that define AI behavior and context
- **Tool**: Executable command/script that AI can invoke
- **Tool Execution**: Record of tool runs with input/output/logs

**Technical**:
- **JWT**: JSON Web Token for authentication
- **ViewSet**: Django REST Framework endpoint collection
- **Serializer**: Data validation and transformation layer
- **Query Key**: TanStack Query cache identifier
- **Mutation**: API write operation (create, update, delete)

---

## Contact & Contributions

For questions or contributions, please contact the project maintainers or open an issue in the project repository.

[Back to Index](./index.md)
