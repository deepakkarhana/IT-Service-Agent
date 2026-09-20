import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to the FastAPI backend, so the frontend code can
// use plain relative URLs and never needs to know the backend port. If port 8020
// is taken on your machine, start the backend elsewhere and set
// VITE_API_TARGET=http://127.0.0.1:<port> before running `npm run dev`.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_TARGET || 'http://127.0.0.1:8020'
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': { target, changeOrigin: true },
      },
    },
  }
})
