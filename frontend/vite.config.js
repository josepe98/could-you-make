import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    target: 'esnext',
  },
  server: {
    port: 5175,
    proxy: {
      '/api': { target: 'https://could-you-make-staging.up.railway.app', changeOrigin: true, secure: true }
    }
  }
})
