import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backend = env.VITE_DEV_PROXY_TARGET || 'http://localhost:8000';

  return {
    plugins: [react(), tailwindcss()],
    // Module workers so the worker can import cryptoService.ts.
    worker: { format: 'es' },
    server: {
      port: 5173,
      // Same-origin in dev: avoids CORS configuration for the simulator.
      proxy: { '/api': { target: backend, changeOrigin: true } },
    },
    build: { sourcemap: false },
  };
});
