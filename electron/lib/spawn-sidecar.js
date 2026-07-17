const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

/**
 * Resolve the absolute path of the bundled Python sidecar binary.
 *
 * In a packaged Electron app the binary lives next to the resources
 * directory. In development/tests a custom `resourcesPath` can be passed
 * to point to a temporary directory containing a fake binary.
 *
 * @param {string} [resourcesPath=process.resourcesPath]
 * @returns {string}
 */
function getSidecarPath(resourcesPath = process.resourcesPath) {
  const name = process.platform === 'win32' ? 'conciliacion-api.exe' : 'conciliacion-api';
  return path.join(resourcesPath, name);
}

/**
 * Spawn the Python sidecar as a detached child process.
 *
 * @param {Object} [options={}]
 * @param {string} [options.resourcesPath] - Directory containing the sidecar binary
 * @param {string} [options.logFile] - Optional file path to pipe stdout/stderr into
 * @param {Object} [options.env={}] - Extra environment variables merged into process.env
 * @returns {import('node:child_process').ChildProcess}
 * @throws {Error} with `code === 'SIDECAR_NOT_FOUND'` when the binary is missing
 */
function spawnSidecar({ resourcesPath, logFile, env = {} } = {}) {
  const sidecar = getSidecarPath(resourcesPath);
  if (!fs.existsSync(sidecar)) {
    const err = new Error(`Sidecar binary not found at ${sidecar}`);
    err.code = 'SIDECAR_NOT_FOUND';
    throw err;
  }
  const proc = spawn(sidecar, [], {
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
    env: { ...process.env, ...env },
  });
  if (logFile) {
    const out = fs.createWriteStream(logFile, { flags: 'a' });
    proc.stdout.pipe(out);
    proc.stderr.pipe(out);
  }
  return proc;
}

module.exports = { getSidecarPath, spawnSidecar };
