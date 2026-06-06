/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'

export default defineConfig({
  // base path: default works for GitHub Pages at /conciliacion-geo-v02/.
  // For a custom domain (e.g. conciliacion-geo.app), set VITE_BASE=/ in
  // the deploy environment.  See web/README-deploy.md.
  base: process.env.VITE_BASE ?? '/conciliacion-geo-v02/',

  plugins: [
    react(),
    tailwindcss(),
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
        // and the browser's normal HTTP cache (Cache-Control +
        // ETag, both set by GitHub Pages) handles those. Heavy
        // chunks (Plotly 4.7 MB) are intentionally excluded from
        // precache because they'd balloon the install event;
        // they're served on demand via the runtime caching rules
        // below instead.
        globPatterns: ['**/*.{js,css,html,ico,png,svg}'],
        globIgnores: ['**/vendor-plotly*.*'],
        additionalManifestEntries: [],
        cleanupOutdatedCaches: true,
        navigateFallbackDenylist: [/assets\/.*-plotly/],
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
  optimizeDeps: {
    include: [
      'mersenne-twister',
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
    // Use polling for file watching. Avoids the inotify ENOSPC
    // issue on systems with many files in node_modules (~33K total). Adds ~50-100ms to HMR but
    // keeps the dev server working on the default 65K watcher
    // limit. Override with the env var VITE_USE_NATIVE_WATCH=true
    // to get faster HMR on systems where you've bumped the limit.
    watch: {
      usePolling: !process.env.VITE_USE_NATIVE_WATCH,
      interval: 200,
      ignored: [
        '**/node_modules/**',
        '**/dist/**',
        '**/.git/**',
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
          'vendor-plotly': ['plotly.js', 'react-plotly.js'],
        },
      },
    },
    // The default warning fires at 500 kB which is fine for a 4 MB
    // Cesium chunk but noisy for the 5 MB main bundle. Bump the
    // threshold so we only see warnings for genuinely large chunks.
    chunkSizeWarningLimit: 2000,
  },
  test: {
    // jsdom for component tests (atoms). Pure domain tests don't need
    // a DOM but we set jsdom as default for consistency.
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      // Domain layer MUST be 100% covered. Other layers are aspirational.
      include: ['src/components/results/ProfileView/domain/**'],
      thresholds: {
        statements: 100,
        branches: 100,
        functions: 100,
        lines: 100,
      },
    },
  },
} as Parameters<typeof defineConfig>[0])
