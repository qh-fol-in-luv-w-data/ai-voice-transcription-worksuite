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
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/files': 'http://127.0.0.1:8000',
      '/private': 'http://127.0.0.1:8000'
    }
  }
}))
