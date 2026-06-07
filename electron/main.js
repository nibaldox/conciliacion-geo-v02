const { app, BrowserWindow, dialog } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { isPortInUse } = require('./lib/port');
const { waitForHealth } = require('./lib/health');

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

function getSidecarPath() {
  const name = process.platform === 'win32' ? 'conciliacion-api.exe' : 'conciliacion-api';
  return path.join(process.resourcesPath, name);
}

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
  const sidecar = getSidecarPath();
  if (!fs.existsSync(sidecar)) {
    throw new Error(`Sidecar binary not found at ${sidecar}`);
  }
  const proc = spawn(sidecar, [], {
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  const out = fs.createWriteStream(logFile, { flags: 'a' });
  proc.stdout.pipe(out);
  proc.stderr.pipe(out);
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

app.whenReady().then(async () => {
  if (await isPortInUse(API_PORT)) {
    fatalError(`El puerto ${API_PORT} ya está en uso. ¿Hay otra instancia de Conciliación corriendo? Ciérrala e intenta de nuevo.`);
    return;
  }

  let logFile;
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

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 768,
    title: 'Conciliación Geotécnica',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.setMenuBarVisibility(false);
  await mainWindow.loadURL(`http://127.0.0.1:${API_PORT}`);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
});

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
  app.quit();
});

app.on('before-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
});
