import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev: proxy /api to the FastAPI backend so the browser sees one origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/healthz': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: { chunkSizeWarningLimit: 2500 },
})
