import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    // livekit-client (~530 kB) is a lazily loaded chunk, fetched only when the
    // user starts talking; the main bundle stays ~210 kB.
    chunkSizeWarningLimit: 600,
  },
  server: {
    port: 5173,
    proxy: {
      // `orion up` serves the API under /api on the same port.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
