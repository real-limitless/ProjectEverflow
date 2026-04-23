# Project Everflow

Project Everflow is a Vite + React landing page focused on safe AI vibecoding for teams. The app uses TypeScript, Tailwind CSS, and shadcn/ui components.

## Docker Compose

This repo now includes separate Compose files and separate container build files for local development and production-style serving.

Development:

```sh
docker compose -f container-compose.dev.yml up --build
```

The development stack builds from `Containerfile.dev`, mounts the repo into the container, installs dependencies with `npm ci`, and serves the app at `http://localhost:8080` with Vite hot reload.

Production-style runtime:

```sh
docker compose -f container-compose.prod.yml up --build -d
```

The production stack builds from `Containerfile.prod` and serves the generated `dist/` directory through Nginx on `http://localhost`. The root `Dockerfile` remains available as the same production build path for direct `docker build` usage.

## Local setup

Requirements:

- Node.js
- npm

Install dependencies and start the development server:

```sh
npm install
npm run dev
```

The default Vite dev server runs on port 8080.

## Available scripts

- `npm run dev` starts the local development server.
- `npm run build` creates a production build in `dist/`.
- `npm run build:dev` creates a development-mode build.
- `npm run preview` serves the production build locally.
- `npm run lint` runs ESLint.
- `npm run test` runs the Vitest suite once.
- `npm run test:watch` runs Vitest in watch mode.

## Deployment notes

Build the app with:

```sh
npm run build
```

Deploy the generated `dist/` directory to any static hosting platform that supports single-page applications. If your host requires route rewrites, configure it to serve `index.html` for client-side routes.

## Stack

- Vite
- React 18
- TypeScript
- Tailwind CSS
- shadcn/ui
- Vitest
