# Project Everflow

## Overview

Project Everflow is an enterprise-grade collaborative AI application development platform enabling teams to build, review, and deploy AI-powered applications with built-in safety, compliance, and approval workflows. It solves the problem of balancing rapid innovation with corporate governance by providing a "governance-first" environment where global compliance, regulatory, and data-handling rules are enforced at the platform level.

Inspired by creative platforms like Hugging Face Spaces, Everflow adds critical oversight to prevent unrestricted development. Users can freely create applications within pre-approved boundaries, ensuring consistency and inherent compliance for all tools.

Key features include:
- Visual workflow builders for AI applications
- Team collaboration and project forking
- AI-assisted project creation via chatbot, checked against corporate guidelines
- Multi-approver change request (PR) workflows with compliance checks
- Global sharing and deployment within the organization

Compared to contemporary tools like Continue, Lovable, v0.dev, or bolt.new, Everflow addresses the gap in managing organizational standards, avoiding "development drift" that leads to fragmented tooling and inconsistent methodologies.

In a typical use case, a support engineer can instantly develop an AI tool to analyze sosreports for system conditions, leveraging pre-configured compliant data access mechanisms (e.g., MCP servers), without triggering lengthy legal reviews.

## Architecture

Project Everflow is built with a modern full-stack architecture:

- **Frontend**: React 18.3.1 with TypeScript, built using Vite for fast development and builds. It integrates PatternFly components for enterprise-grade UI, Tailwind CSS for styling, and includes libraries like ReactFlow for visual workflow builders, TanStack Query for state management, and Recharts for data visualization.
- **Backend**: Django 4.x with Django REST Framework, providing a robust API layer. Uses SQLite for development and PostgreSQL for production. Includes features like user management, project tracking, change requests (PRs), compliance checks, and AI tooling integration.
- **Key Libraries**: React Hook Form + Zod for form validation, Lucide for icons, and custom components for dashboards, editors, and project modules.
- **API Surface**: Endpoints include `/api/users/`, `/api/projects/`, `/api/change-requests/`, `/api/compliance-checks/`, `/api/compliance-templates/`, `/api/project-assignments/`.
- **Deployment**: Containerized using Podman/Docker, with compose files for local development. Supports build and preview workflows.

For detailed architecture and component breakdowns, see [`docs/agents/index.md`](docs/agents/index.md).

## Installation

To set up Project Everflow locally, follow these steps. Ensure you have Node.js, npm, Python 3.x, and pip installed.

### Prerequisites
- Node.js & npm (install with [nvm](https://github.com/nvm-sh/nvm#installing-and-updating))
- Python 3.x and pip
- Git

### Steps

1. **Clone the repository**:
   ```sh
   git clone <YOUR_GIT_URL>
   cd <YOUR_PROJECT_NAME>
   ```

2. **Set up the backend**:
   ```sh
   cd backend
   pip install -r requirements.txt
   python manage.py migrate
   python manage.py runserver
   ```
   The backend will run on `http://localhost:8000` by default.

3. **Set up the frontend** (in a new terminal):
   ```sh
   cd ..  # Back to project root
   npm install
   npm run dev
   ```
   The frontend will run on `http://localhost:5173` by default.

4. **Access the application**:
   Open your browser and navigate to `http://localhost:5173` for the frontend. The backend API is available at `http://localhost:8000`.

### Additional Notes
- For development, you may need to configure environment variables or API endpoints. Check `backend/settings.py` and `src/lib/api.ts` for configuration details.
- If using containers, refer to `podman-compose.yml` or `Containerfile` for containerized setup.
- Run tests with `npm test` for frontend and `python manage.py test` for backend.

### Using Podman Containers

As an alternative to manual setup, you can run the application using Podman containers.

#### Prerequisites
- Podman installed (see [Podman installation guide](https://podman.io/getting-started/installation))

#### Steps
1. **Clone the repository** (if not already done):
   ```sh
   git clone <YOUR_GIT_URL>
   cd <YOUR_PROJECT_NAME>
   ```

2. **Run the containers**:
   ```sh
   podman-compose up
   ```
   This will build and start the frontend and backend services. The frontend will be available at `http://localhost:5173` and the backend at `http://localhost:8000`.

3. **Access the application**:
   Open your browser and navigate to `http://localhost:5173`.

## Technologies Used

This project is built with:

- **Frontend**: Vite, TypeScript, React, PatternFly, shadcn-ui, Tailwind CSS
- **Backend**: Django, Django REST Framework, SQLite/PostgreSQL
- **Other**: ReactFlow, TanStack Query, React Hook Form, Zod, Recharts, Lucide

## Deployment

To deploy Project Everflow:

- Use the provided `Containerfile` and `podman-compose.yml` for containerized deployment.
- For cloud deployment, build and push images to your registry, then deploy using orchestration tools like Kubernetes.
- Alternatively, use Lovable for quick previews: Open [Lovable](https://lovable.dev/projects/09b404b7-7956-4600-bea8-ea7a8793a5a5) and click on Share -> Publish.

## Custom Domain

You can connect a custom domain via Lovable: Navigate to Project > Settings > Domains and click Connect Domain. Read more [here](https://docs.lovable.dev/features/custom-domain#custom-domain).

## Contributing

For development guidelines, workflows, and more details, refer to the documentation in [`docs/agents/`](docs/agents/).

## Support

For support, glossary, and contact information, see [`docs/agents/support.md`](docs/agents/support.md).
