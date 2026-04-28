/**
 * CesiumJS configuration — must be imported BEFORE any Cesium imports.
 * Sets the base URL for static assets (Workers, Assets, Widgets).
 * Assets are served from public/Cesium/ (copied by vite plugin at build time).
 */
(window as unknown as Record<string, string>).CESIUM_BASE_URL = '/Cesium';
