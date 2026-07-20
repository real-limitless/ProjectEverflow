const SNIPPETS: Record<string, string> = {
  'podman-compose.yml': `services:
  nginx-proxy:
    image: nginx:alpine
    ports:
      - "80:80"
    depends_on:
      - node-api
  node-api:
    image: everflow/api:latest
    environment:
      - DATABASE_URL
      - NODE_ENV=production
    ports:
      - "8000:8000"
  postgres-db:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
  redis-cache:
    image: redis:7-alpine

volumes:
  pgdata:
`,
  'podman-compose.staging.yml': `services:
  web:
    image: everflow/web:staging
    ports:
      - "80:8080"
  api:
    image: everflow/api:staging
    environment:
      - DATABASE_URL
      - OPENROUTER_API_KEY
  worker:
    image: everflow/worker:staging
  redis:
    image: redis:7-alpine
`,
  'compose.preview.yml': `services:
  web:
    image: everflow/web:preview
    ports:
      - "5173:5173"
  api:
    image: everflow/api:preview
    ports:
      - "8000:8000"
    environment:
      - VITE_API_URL
`,
}

export function composeSnippet(file: string): string {
  return (
    SNIPPETS[file] ??
    `services:
  app:
    image: everflow/app:latest
    # demo snippet for ${file}
`
  )
}

export const DEPLOY_ENVS = ['Preview', 'Staging', 'Production'] as const

export function defaultComposeForEnv(env: string, files: string[]): string {
  if (env === 'Preview' && files.some((f) => f.includes('preview'))) {
    return files.find((f) => f.includes('preview'))!
  }
  if (env === 'Staging' && files.some((f) => f.includes('staging'))) {
    return files.find((f) => f.includes('staging'))!
  }
  return files[0] ?? 'podman-compose.yml'
}
