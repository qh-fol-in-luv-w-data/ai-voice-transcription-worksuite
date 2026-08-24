import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// Nơi bench đang chạy. Trước đây ghi cứng cổng 8001/9000, đến khi bench đổi
// cổng thì dev server gọi vào chỗ không có ai phục vụ và mọi lời gọi API đều
// hỏng — mà lỗi lại hiện ra dưới dạng màn hình trắng nên rất khó đoán. Ai
// chạy cổng khác thì đặt biến môi trường, khỏi phải sửa file rồi lỡ commit.
const BENCH_URL = process.env.VOICE_BENCH_URL || 'http://ct-datalake.localhost:8002'
const SOCKET_URL = process.env.VOICE_SOCKET_URL || 'http://ct-datalake.localhost:9002'

export default defineConfig(({ command }) => ({
  plugins: [vue()],
  base: command === 'serve' ? '/' : '/assets/voice_app/frontend/',
  build: {
    outDir: path.resolve(__dirname, '../voice_app/public/frontend'),
    emptyOutDir: true
  },
  server: {
    port: 5174,
    // Mặc định Vite chỉ nghe trên ::1, nên trình duyệt nào đi bằng 127.0.0.1
    // sẽ không vào được.
    host: '0.0.0.0',
    proxy: {
      '/api': { target: BENCH_URL, changeOrigin: true },
      '/files': { target: BENCH_URL, changeOrigin: true },
      '/private': { target: BENCH_URL, changeOrigin: true },
      // Trang đăng nhập và tài nguyên đi kèm do Frappe phục vụ; thiếu mấy
      // đường này thì lúc chưa đăng nhập, dev server không có gì để trả và
      // màn hình chỉ còn một khoảng trắng.
      '/login': { target: BENCH_URL, changeOrigin: true },
      '/assets': { target: BENCH_URL, changeOrigin: true },
      '/app': { target: BENCH_URL, changeOrigin: true },
      '/socket.io': { target: SOCKET_URL, changeOrigin: true, ws: true }
    }
  }
}))
