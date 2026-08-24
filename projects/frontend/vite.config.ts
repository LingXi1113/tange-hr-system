import { fileURLToPath, URL } from 'node:url';

import react from '@vitejs/plugin-react';
import { defineConfig, type PluginOption } from 'vite';

type ProjectType = 'embedded' | 'normal';

const JAHEAD_JSSDK_URL =
  'https://cdn.jahead.com/jahead-jssdk/v0.1.0/jahead-jssdk.js';

const createJaheadSdkPlugin = (projectType: ProjectType): PluginOption => ({
  name: 'inject-jahead-jssdk',
  transformIndexHtml() {
    if (projectType !== 'embedded') {
      return [];
    }

    return [
      {
        tag: 'script',
        attrs: {
          src: JAHEAD_JSSDK_URL,
        },
        injectTo: 'head',
      },
    ];
  },
});

export default defineConfig(() => {
  const env = process.env;
  const projectType: ProjectType = env.PROJECT_TYPE === 'embedded' ? 'embedded' : 'normal';
  const appId = projectType === 'embedded' ? env.APP_ID || env.OPEN_PLATFORM_APP_ID || '' : '';
  const projectId = env.PROJECT_ID || '';
  const companyId = env.COMPANY_ID || '';
  const trackingEndpoint = env.TRACKING_ENDPOINT || '';

  return {
    envDir: false,
    define: {
      __APP_ID__: JSON.stringify(appId),
      __COMPANY_ID__: JSON.stringify(companyId),
      __PROJECT_ID__: JSON.stringify(projectId),
      __PROJECT_TYPE__: JSON.stringify(projectType),
      __TRACKING_ENDPOINT__: JSON.stringify(trackingEndpoint),
    },
    plugins: [react(), createJaheadSdkPlugin(projectType)],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      allowedHosts: true,
      hmr: {
        path: '/vite-hmr',
      },
      port: Number(env.VITE_DEV_PORT) || 5173,
      // 开发联调代理：同源 /api、/env 转发到后端 8100（仅 dev server 生效；
      // 生产由 nginx 转发，不依赖此配置）。
      proxy: {
        '/api': {
          target: env.HRATS_DEV_PROXY_TARGET || 'http://127.0.0.1:8100',
          changeOrigin: true,
        },
        '/env': {
          target: env.HRATS_DEV_PROXY_TARGET || 'http://127.0.0.1:8100',
          changeOrigin: true,
        },
      },
    },
    preview: {
      port: Number(env.VITE_PREVIEW_PORT) || 4173,
    },
    build: {
      chunkSizeWarningLimit: 1200,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) {
              return undefined;
            }

            if (id.includes('/antd/') || id.includes('/@ant-design/')) {
              return 'antd';
            }

            if (id.includes('/axios/')) {
              return 'axios';
            }

            if (
              id.includes('/react/') ||
              id.includes('/react-dom/') ||
              id.includes('/react-router-dom/')
            ) {
              return 'react';
            }

            return undefined;
          },
        },
      },
    },
  };
});
