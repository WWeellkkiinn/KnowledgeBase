import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

// dev 期前后端分跑：5173 前 + 5000 后。
// 代理走 server.proxy，生产环境由反代/同源部署接管，前端代码统一用相对路径 `/api`。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: false,
      },
      '/socket.io': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: false,
        ws: true,
      },
    },
  },
})
