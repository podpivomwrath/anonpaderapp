import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Локально проксируем запросы к тому же aiohttp-серверу, что и бот
    // (main.py, порт из PORT/.env) — без этого понадобился бы CORS и для dev.
    proxy: {
      '/api/miniapp': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
