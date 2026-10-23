import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In dev, forward backend paths to FastAPI so React can use relative URLs
// like fetch('/api/projects') with no CORS trouble.
const backend = 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': backend,
      '/upload': backend,
      '/jobs': backend,
      '/clips': backend,
    },
  },
})
