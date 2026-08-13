import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/rooms': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/session': 'http://localhost:8000',
      '/upload': 'http://localhost:8000',
      '/generate': 'http://localhost:8000',
      '/questions': 'http://localhost:8000',
      '/concepts': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
