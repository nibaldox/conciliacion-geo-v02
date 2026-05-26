import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import { copyFileSync, mkdirSync, existsSync, readdirSync, rmSync, statSync } from 'fs'
import { resolve, join } from 'path'

/**
 * Vite plugin to copy Cesium static assets to public/Cesium.
 * Cesium workers, assets, and widgets must be served from the public directory
 * to avoid Vite's dependency optimization interfering with their loading.
 */
function cesiumStaticAssets() {
  const cesiumSource = resolve(__dirname, 'node_modules/cesium/Build/Cesium')
  const cesiumDest = resolve(__dirname, 'public/Cesium')

  return {
    name: 'cesium-static-assets',
    buildStart() {
      // Clean previous assets
      if (existsSync(cesiumDest)) {
        rmSync(cesiumDest, { recursive: true })
      }
      mkdirSync(cesiumDest, { recursive: true })

      // Copy Cesium static files recursively
      function copyDir(src: string, dest: string) {
        if (!existsSync(dest)) {
          mkdirSync(dest, { recursive: true })
        }
        for (const entry of readdirSync(src)) {
          const srcPath = join(src, entry)
          const destPath = join(dest, entry)
          const stat = statSync(srcPath)
          if (stat.isDirectory()) {
            copyDir(srcPath, destPath)
          } else {
            copyFileSync(srcPath, destPath)
          }
        }
      }

      copyDir(cesiumSource, cesiumDest)
      console.log('[cesium-static-assets] Copied Cesium assets to public/Cesium')
    },
  }
}

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    cesiumStaticAssets(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  // Exclude cesium from dependency optimization to prevent bundling issues
  // with its workers and CJS/ESM mixed structure
  optimizeDeps: {
    exclude: ['cesium'],
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor-react': ['react', 'react-dom'],
          'vendor-chartjs': ['chart.js', 'react-chartjs-2'],
          'vendor-tanstack': ['@tanstack/react-query', '@tanstack/react-table'],
          'vendor-cesium': ['cesium'],
        },
      },
    },
  },
})
