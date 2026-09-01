import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/workflows': 'http://localhost:8001',
      '/resources': 'http://localhost:8000',
    },
  },
})
