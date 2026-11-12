import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode, command }) => {
  const environmentDirectory = fileURLToPath(new URL('..', import.meta.url))
  const env = loadEnv(mode, environmentDirectory, 'VITE_')
  const apiBase = env.VITE_API_BASE_URL || '/api'
  const assetBase = env.VITE_ASSET_BASE_URL?.trim()
  if (command === 'build' && assetBase) {
    const url = new URL(assetBase)
    if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) {
      throw new Error('VITE_ASSET_BASE_URL 必须是无凭据、查询参数或片段的 HTTPS 地址')
    }
  }

  return {
    envDir: environmentDirectory,
    base: command === 'build' && assetBase ? `${assetBase.replace(/\/+$/, '')}/` : '/',
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
    },
  }
})
