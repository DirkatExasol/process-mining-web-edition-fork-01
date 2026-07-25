import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // `npm run dev` talks to the compute backend directly; in production the
    // Python GUI server performs the same proxying. The backend serves TLS with
    // a self-signed internal cert, so target HTTPS and skip cert verification
    // (dev only — the Python proxy pins the cert in production).
    proxy: {
      '/api': {
        target: process.env.PMW_BACKEND_URL ?? 'https://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1500,
  },
})
