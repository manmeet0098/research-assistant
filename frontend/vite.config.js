import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The FastAPI backend runs on :8000; proxy /api so the browser sees one origin.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/**/*.test.{js,jsx}', 'src/test/**', 'src/main.jsx'],
      reporter: ['text'],
      reportOnFailure: true,
    },
  },
})
