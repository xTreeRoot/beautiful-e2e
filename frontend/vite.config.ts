import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

function vendorChunkName(id: string) {
  if (!id.includes('node_modules')) return undefined;

  const packagePath = id.split('node_modules/')[1];
  const [scopeOrName, scopedName] = packagePath.split('/');
  const packageName = scopeOrName.startsWith('@') ? `${scopeOrName}/${scopedName}` : scopeOrName;

  // 大体积且变化较慢的界面/运行时依赖保持在稳定分块中，便于缓存。
  if (['react', 'react-dom', 'scheduler'].includes(packageName)) return 'vendor-react';
  if (packageName.startsWith('@xyflow/')) return 'vendor-flow';
  if (packageName === 'lucide-react') return 'vendor-icons';
  if (packageName === 'antd') return 'vendor-antd';
  if (
    packageName.startsWith('rc-') ||
    packageName.startsWith('@rc-component/') ||
    packageName.startsWith('@ant-design/')
  ) {
    return 'vendor-antd-helpers';
  }

  return 'vendor';
}

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: vendorChunkName
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true
      }
    }
  }
});
