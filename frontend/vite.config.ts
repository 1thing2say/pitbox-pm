import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API and the UI are separate dev servers but the same origin in production,
// so /api is proxied through Vite in dev. That keeps every fetch call relative
// ('/api/projects') — no base URL to configure, no CORS to enable.
//
// Build output goes to frontend/dist, which FastAPI serves in preference to the
// old static/ folder when it exists (see app/main.py).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
