const { app, BrowserWindow, dialog } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { isPortInUse } = require('./lib/port');
const { waitForHealth } = require('./lib/health');
const { isDevMode, getDevUrl } = require('./lib/dev-mode');
const { spawnSidecar } = require('./lib/spawn-sidecar');
const { showSplash, closeSplash } = require('./lib/splash');
const { installAppMenu } = require('./lib/menu');

const API_PORT = 57890;
let pythonProcess = null;
let mainWindow = null;

// Use a per-user-data-dir under the data directory so the Chromium
// cache (and any stale Service Worker registrations) don't survive
// across installs of the AppImage. This also avoids the well-known
// "black screen after upgrade" caused by a cached index.html
// referencing asset hashes from a previous build.
app.setPath('userData', path.join(
  process.env.APPDATA
    || (process.platform === 'darwin'
      ? path.join(os.homedir(), 'Library', 'Application Support')
      : path.join(os.homedir(), '.local', 'share')),
  'conciliacion',
  'chromium'
));

function getLogFile() {
  if (process.platform === 'win32') {
    return path.join(process.env.APPDATA || os.homedir(), 'conciliacion', 'logs', 'conciliacion.log');
  }
  const xdg = process.env.XDG_DATA_HOME || path.join(os.homedir(), '.local', 'share');
  return path.join(xdg, 'conciliacion', 'logs', 'conciliacion.log');
}

function setupSidecarLogging() {
  const logFile = getLogFile();
  fs.mkdirSync(path.dirname(logFile), { recursive: true });
  return logFile;
}

function startSidecar(logFile) {
  const proc = spawnSidecar({ logFile });
  proc.on('exit', (code) => {
    if (code !== 0 && code !== null && mainWindow && !mainWindow.isDestroyed()) {
      console.error(`Sidecar exited with code ${code}`);
    }
  });
  return proc;
}

function fatalError(message) {
  dialog.showErrorBox('Conciliación Geotécnica — Error', message);
  app.quit();
}

function killPythonProcess() {
  if (pythonProcess) {
    if (process.platform === 'win32') {
      // On Windows, PyInstaller onefile bundles run in a wrapper/bootloader process.
      // A standard pythonProcess.kill() only terminates the parent bootloader process,
      // leaving the actual child Python process alive and holding the port.
      // We use taskkill with /T (tree kill) and /F (force) to clean up the entire tree.
      spawn('taskkill', ['/pid', pythonProcess.pid.toString(), '/f', '/t'], {
        stdio: 'ignore',
        detached: true
      });
    } else {
      pythonProcess.kill();
    }
    pythonProcess = null;
  }
}

// Disable GPU when running under Xvfb (no real GL extensions). The
// user (or dev-electron.sh) sets ELECTRON_DISABLE_GPU=1; we also
// support passing --disable-gpu on the command line. Must be called
// BEFORE app.whenReady() resolves.
if (process.env.ELECTRON_DISABLE_GPU === '1'
    || process.argv.includes('--disable-gpu')) {
  app.disableHardwareAcceleration();
}

app.whenReady().then(async () => {
  const iconPath = path.join(__dirname, 'assets', 'icon.png');
  const splash = showSplash({ iconPath });
  let logFile;

  try {
    if (!isDevMode()) {
      if (await isPortInUse(API_PORT)) {
        fatalError(`El puerto ${API_PORT} ya está en uso. ¿Hay otra instancia de Conciliación corriendo? Ciérrala e intenta de nuevo.`);
        return;
      }

      try {
        logFile = setupSidecarLogging();
        pythonProcess = startSidecar(logFile);
      } catch (err) {
        fatalError(`No se pudo iniciar el backend: ${err.message}`);
        return;
      }

      try {
        await waitForHealth(API_PORT, 15000, 200);
      } catch (err) {
        fatalError(`El backend no respondió a tiempo. Revisá el log en ${logFile}`);
        return;
      }
    }

    mainWindow = new BrowserWindow({
      width: 1280,
      height: 800,
      minWidth: 1024,
      minHeight: 768,
      title: 'Conciliación Geotécnica',
      icon: iconPath,
      show: false,
      webPreferences: {
        preload: path.join(__dirname, 'preload.js'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
      },
    });

    installAppMenu(mainWindow);

    const targetUrl = isDevMode() ? getDevUrl() : `http://127.0.0.1:${API_PORT}`;
    await mainWindow.loadURL(targetUrl);
    mainWindow.show();

    mainWindow.on('closed', () => {
      mainWindow = null;
    });
  } finally {
    closeSplash(splash);
  }
});

app.on('window-all-closed', () => {
  killPythonProcess();
  app.quit();
});

app.on('before-quit', () => {
  killPythonProcess();
});
