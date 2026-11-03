import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { spawn } from 'node:child_process'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'start-meditriage-backend',
      configureServer(server) {
        const backend = spawn('python', ['-u', 'backend/chatbot/chatbot_server.py'], {
          cwd: process.cwd(),
          stdio: 'inherit',
          shell: process.platform === 'win32',
        })

        server.httpServer?.once('close', () => backend.kill())
      },
    },
  ],
  server: {
    proxy: {
      '/chatbot': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
})
