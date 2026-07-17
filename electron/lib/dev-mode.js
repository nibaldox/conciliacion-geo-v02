/**
 * Helpers for Electron development mode.
 *
 * When `CONCILIACION_ELECTRON_DEV=1` is set, the Electron main process skips
 * spawning the PyInstaller sidecar and loads the React app from the Vite dev
 * server instead of the bundled static build.
 */

/**
 * @returns {boolean}
 */
function isDevMode() {
  return process.env.CONCILIACION_ELECTRON_DEV === '1';
}

/**
 * @returns {string}
 */
function getDevUrl() {
  return process.env.CONCILIACION_DEV_URL || 'http://localhost:5173';
}

module.exports = { isDevMode, getDevUrl };
