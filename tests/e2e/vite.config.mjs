import path from 'node:path';
import { createRequire } from 'node:module';
const root = path.resolve(import.meta.dirname, '../..');
const envDir = process.env.VTT_E2E_ENV_DIR;
if (!envDir) throw new Error('Explicit empty temporary env directory required');
const require = createRequire(path.join(root, 'frontend/package.json'));
const { defineConfig } = require('vite');
const react = require('@vitejs/plugin-react').default;
export default defineConfig({ root, publicDir: path.join(root, 'frontend/public'), envDir, plugins: [react(), { name: 'explicit-local-acceptance',
  configureServer(server) { server.middlewares.use((req, _res, next) => {
    if (req.headers.accept?.includes('text/html') && !req.url?.startsWith('/api/') && !req.url?.startsWith('/__e2e/')) req.url='/tests/e2e/native.html';
    next();
  }); }
}], optimizeDeps: { include: ['react', 'react-dom/client', 'react/jsx-runtime'] },
resolve: { alias: { 'react': path.join(root,'frontend/node_modules/react'), 'react-dom': path.join(root,'frontend/node_modules/react-dom') } },
server: { host:'127.0.0.1', port:Number(process.env.VTT_E2E_WEB_PORT || 5190), strictPort:true,
 proxy: { '/api': { target:`http://127.0.0.1:${process.env.VTT_E2E_API_PORT || 18010}`, ws:true },
 '/__e2e':`http://127.0.0.1:${process.env.VTT_E2E_API_PORT || 18010}`,
 '/__test_storage':`http://127.0.0.1:${process.env.VTT_E2E_API_PORT || 18010}` } } });
