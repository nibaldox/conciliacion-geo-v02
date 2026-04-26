/**
 * CesiumJS configuration — must be imported BEFORE any Cesium imports.
 * Sets the base URL for static assets (Workers, Assets, Widgets).
 */
(window as unknown as Record<string, string>).CESIUM_BASE_URL = '/';
