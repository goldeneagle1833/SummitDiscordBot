import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:5000',
      '/avatar-images': 'http://127.0.0.1:5000',
      '/card-images': 'http://127.0.0.1:5000',
      '/static': 'http://127.0.0.1:5000',
      '/auth': 'http://127.0.0.1:5000',
    },
  },
})
