import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

const usePolling =
  process.env.VITE_USE_POLLING === 'true' ||
  process.env.CHOKIDAR_USEPOLLING === 'true'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    // 0.0.0.0 so the dev server is reachable from outside Docker
    host: true,
    port: 5173,
    watch: usePolling
      ? {
          usePolling: true,
        }
      : undefined,
  },
})
