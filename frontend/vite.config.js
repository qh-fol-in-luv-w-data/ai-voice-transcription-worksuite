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
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        headers: { Host: 'ct-datalake.localhost' }
      },
      '/files': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        headers: { Host: 'ct-datalake.localhost' }
      },
      '/private': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        headers: { Host: 'ct-datalake.localhost' }
      }
    }
  }
}))
