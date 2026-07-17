const path = require('node:path');
const { execSync } = require('node:child_process');

/**
 * electron-builder config for the portable bundle.
 *
 * The Python sidecar (built with PyInstaller, see ../../conciliacion-api.spec)
 * is expected at:
 *   ../dist/conciliacion-api(.exe)
 *
 * Build:
 *   npm run build:windows  -> ../dist-portable/conciliacion-portable-windows/
 *   npm run build:linux    -> ../dist-portable/conciliacion-portable-linux.AppImage
 */

function getBuildVersion() {
  try {
    return execSync('bash ../scripts/version.sh', { cwd: __dirname, encoding: 'utf8' }).trim();
  } catch {
    return require('./package.json').version;
  }
}

module.exports = {
  appId: 'app.conciliacion.geotecnica',
  productName: 'Conciliación Geotécnica',
  copyright: 'Copyright © 2026',
  buildVersion: getBuildVersion(),
  extraMetadata: {
    version: getBuildVersion(),
  },

  directories: {
    output: path.join(__dirname, '..', 'dist-portable'),
    buildResources: path.join(__dirname, 'assets'),
  },

  files: [
    'main.js',
    'preload.js',
    'lib/**/*',
    'assets/**/*',
    'package.json',
  ],

  extraResources: [
    {
      from: path.join(__dirname, '..', 'dist', 'conciliacion-api.exe'),
      to: 'conciliacion-api.exe',
      filter: ['**/*'],
    },
    {
      from: path.join(__dirname, '..', 'dist', 'conciliacion-api'),
      to: 'conciliacion-api',
      filter: ['**/*'],
    },
  ],

  win: {
    target: [{ target: 'dir', arch: ['x64'] }],
    artifactName: 'conciliacion-portable-windows',
  },

  linux: {
    target: [{ target: 'AppImage', arch: ['x64'] }],
    artifactName: 'conciliacion-portable-linux.AppImage',
    category: 'Science',
  },

  // Sin auto-update en v1
  publish: null,
};
