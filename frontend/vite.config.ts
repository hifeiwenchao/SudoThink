import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode, command }) => {
  const environmentDirectory = fileURLToPath(new URL('..', import.meta.url))
  const env = loadEnv(mode, environmentDirectory, ['VITE_', 'CDN_BASE_URL', 'OSS_STATIC_PREFIX'])
  const apiBase = env.VITE_API_BASE_URL || '/api'
  const cdnBase = env.CDN_BASE_URL
  let assetBase = '/'
  if (command === 'build' && cdnBase) {
    const url = new URL(cdnBase)
    if (!/^https:\/\//i.test(cdnBase) || !url.hostname || url.protocol !== 'https:'
      || url.username || url.password || /[\s?#]/.test(cdnBase)) {
      throw new Error('CDN_BASE_URL 必须是无凭据、空白、查询参数或片段的完整 HTTPS 地址')
    }
    const staticPrefix = (env.OSS_STATIC_PREFIX ?? 'static').replace(/^\/+|\/+$/g, '')
    if (!/^[A-Za-z0-9_./-]+$/.test(staticPrefix)
      || staticPrefix.split('/').some((part) => !part || part === '.' || part === '..')) {
      throw new Error('OSS_STATIC_PREFIX 只能包含字母、数字、下划线、点、短横线和目录分隔符，且不能包含空目录或路径穿越')
    }
    assetBase = `${cdnBase.replace(/\/+$/, '')}/${staticPrefix}/`
  }

  return {
    envDir: environmentDirectory,
    base: assetBase,
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '0.0.0.0',
      port: 8100,
      allowedHosts: ['www.feiwenchao.com', 'admin.feiwenchao.com'],
      proxy: {
        [apiBase]: {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: false,
      rollupOptions: {
        output: {
          entryFileNames: 'assets/[name].js',
          chunkFileNames: 'assets/[name].js',
          assetFileNames: 'assets/[name][extname]',
        },
      },
    },
  }
})
