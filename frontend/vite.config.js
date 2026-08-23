import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig(({ command }) => ({
  plugins: [vue()],
  base: command === 'serve' ? '/' : '/assets/voice_app/frontend/',
  build: {
    outDir: path.resolve(__dirname, '../voice_app/public/frontend'),
    emptyOutDir: true
  },
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: true
      },
      '/files': {
        target: 'http://localhost:8001',
        changeOrigin: true
      },
      '/private': {
        target: 'http://localhost:8001',
        changeOrigin: true
      },
      '/socket.io': {
        target: 'http://localhost:9000',
        changeOrigin: true,
        ws: true
      }
    }
  }
}))
