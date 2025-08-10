import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/search': 'http://localhost:8000',
      '/index':  'http://localhost:8000',
      '/status': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/doc':    'http://localhost:8000',
      '/config':    'http://localhost:8000'
    }
  }
})
