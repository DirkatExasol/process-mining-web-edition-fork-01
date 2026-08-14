import { fileURLToPath, URL } from 'node:url'
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
    rollupOptions: {
      // Entry points sharing one dist/ (and chunked vendor code): the main app
      // (index.html), the integration console (integration.html) and the Actions
      // authoring surface (actions.html). Each Python surface serves its own shell.
      input: {
        main: fileURLToPath(new URL('./index.html', import.meta.url)),
        integration: fileURLToPath(new URL('./integration.html', import.meta.url)),
        actions: fileURLToPath(new URL('./actions.html', import.meta.url)),
      },
    },
  },
})
