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
  // base path: default works for GitHub Pages at /conciliacion-geo-v02/.
  // For a custom domain (e.g. conciliacion-geo.app), set VITE_BASE=/ in
  // the deploy environment.  See web/README-deploy.md.
  base: process.env.VITE_BASE ?? '/conciliacion-geo-v02/',

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
    // cesium pulls in several CJS-only dependencies that Vite's esbuild
    // pre-bundler otherwise tries to import as ESM and breaks with
    // "does not provide an export named 'default'". We keep cesium itself
    // excluded (it's loaded from public/Cesium via the static-assets
    // plugin), but its CJS transitive deps must be pre-bundled. Same
    // applies to mersenne-twister, a Plotly dependency.
    include: [
      'mersenne-twister',
      'urijs',
      'protobufjs',
      'dompurify',
      'autolinker',
      'lerc',
      'meshoptimizer',
      'rbush',
      'topojson-client',
      'bit-twiddle',
      'grapheme-splitter',
      'draco3d',
      'earcut',
      'ktx-parse',
      'bitmap-sdf',
    ],
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
