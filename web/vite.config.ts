import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The build goes inside the Python package, where `fitlib serve` serves it from.
// In development (`npm run dev`), API calls go to a `fitlib serve` on port 8000.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../src/fitlib/web_dist',
    emptyOutDir: true,
    // ECharts is one ~550 kB chunk, loaded only on a ride's page; fine for a local app.
    chunkSizeWarningLimit: 600,
  },
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  test: {
    include: ['src/**/*.test.ts'],
  },
})
