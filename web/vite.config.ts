import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
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
    VitePWA({
      // Register the service worker that Workbox generates. We do NOT
      // include the Cesium static assets (~22 MB) or the heavy lazy
      // chunks (Cesium 5.5 MB, Plotly 4.7 MB) in the precache —
      // they're only useful when the user opts into the 3D viewer /
      // Plotly plan view, and precaching them on first install would
      // balloon the install event by ~30 MB. They're served via
      // runtime caching rules instead.
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'robots.txt', 'manifest.webmanifest'],
      manifest: false,                 // we ship our own /manifest.webmanifest
      workbox: {
        // No precache — we have only ~6 small initial-load assets
        // and the browser's normal HTTP cache (Cache-Control +
        // ETag, both set by GitHub Pages) handles those. Heavy
        // chunks (Cesium 5.5 MB, Plotly 4.7 MB) and the Cesium
        // static tree (22 MB) are intentionally excluded from
        // precache because they'd balloon the install event;
        // they're served on demand via the runtime caching rules
        // below instead. The Cesium static tree is also kept out
        // of navigateFallback so deep links into /Cesium/* never
        // try to use the SPA index.
        globPatterns: [],
        additionalManifestEntries: [],
        cleanupOutdatedCaches: true,
        navigateFallbackDenylist: [/Cesium\//, /assets\/.*-(cesium|plotly)/],
        runtimeCaching: [
          {
            // Demo data + small static assets: cache-first
            urlPattern: /\/(demo|icons|og)\/.*\.(stl|dxf|png|json)$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'static-demo-assets',
              expiration: { maxEntries: 50, maxAgeSeconds: 60 * 60 * 24 * 7 },
            },
          },
          {
            // Cesium JS chunk (when the user actually loads the 3D
            // viewer): cache-first so subsequent visits don't refetch
            // the 4 MB. Static assets (Workers, Widgets) get their own
            // cache so we don't mix concerns.
            urlPattern: /\/assets\/.*-cesium.*\.js$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'cesium-js',
              expiration: { maxEntries: 5, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
          {
            // Cesium static assets (Workers, Widgets, etc.) — these
            // are referenced by absolute URL via CESIUM_BASE_URL.
            urlPattern: /\/Cesium\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'cesium-assets',
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
          {
            // Plotly: cache-first
            urlPattern: /\/assets\/.*-plotly.*\.js$/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'plotly-js',
              expiration: { maxEntries: 5, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
          {
            // API responses (stale-while-revalidate for 1 day).
            urlPattern: /\/api\/v1\/.*/,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 },
            },
          },
          {
            // Google Fonts: cache-first (with long TTL)
            urlPattern: /^https:\/\/fonts\.(googleapis|gstatic)\.com\/.*/,
            handler: 'CacheFirst',
            options: {
              cacheName: 'google-fonts',
              expiration: { maxEntries: 10, maxAgeSeconds: 60 * 60 * 24 * 365 },
            },
          },
        ],
      },
      devOptions: {
        // Don't enable the SW in dev — it gets in the way of HMR.
        enabled: false,
      },
    }),
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
    // public/Cesium/ has ~thousands of files (Workers, Assets,
    // Widgets) copied at build time. Watching them exhausts the
    // inotify limit (ENOSPC) on most Linux systems. They're served
    // as static assets by Vite's dev server without watching, so
    // this is purely a HMR optimisation.
    watch: {
      ignored: [
        '**/public/Cesium/**',
        '**/node_modules/**',
        '**/dist/**',
      ],
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
          'vendor-plotly': ['plotly.js', 'react-plotly.js'],
        },
      },
    },
    // The default warning fires at 500 kB which is fine for a 4 MB
    // Cesium chunk but noisy for the 5 MB main bundle. Bump the
    // threshold so we only see warnings for genuinely large chunks.
    chunkSizeWarningLimit: 2000,
  },
})
