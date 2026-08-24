import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8011',
        changeOrigin: true
      }
    }
  },
  build: {
    // Build straight into the repo-root static/ dir that FastAPI serves,
    // so the production bundle can be committed for single-stage deploys.
    outDir: '../static',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1600
  }
})