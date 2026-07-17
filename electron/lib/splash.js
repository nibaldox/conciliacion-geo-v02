const { BrowserWindow } = require('electron');
const path = require('node:path');

/**
 * Show a splash window while the sidecar starts.
 * The splash is a small frameless window with the app logo and a "Loading..."
 * message. The user sees it immediately, before the main window.
 *
 * @param {object} options
 * @param {string} options.iconPath - absolute path to the app icon
 * @param {string} [options.message='Iniciando Conciliación Geotécnica...']
 * @returns {BrowserWindow}
 */
function showSplash({ iconPath, message = 'Iniciando Conciliación Geotécnica...' }) {
  const splash = new BrowserWindow({
    width: 400,
    height: 300,
    frame: false,
    alwaysOnTop: true,
    transparent: false,
    backgroundColor: '#1a1a1a',
    icon: iconPath,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  // Render the splash as inline HTML (no separate file needed)
  splash.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(`
    <!DOCTYPE html>
    <html>
    <head>
      <style>
        body {
          background: linear-gradient(135deg, #1a1a1a 0%, #2a2a3a 100%);
          color: white;
          font-family: -apple-system, BlinkMacSystemFont, sans-serif;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100vh;
          margin: 0;
          user-select: none;
        }
        .icon {
          width: 80px; height: 80px; border-radius: 16px;
          background: #2F5496; display: flex; align-items: center;
          justify-content: center; font-size: 40px; font-weight: bold;
          margin-bottom: 24px;
        }
        h1 { font-size: 1.2rem; margin: 0 0 8px; font-weight: 500; }
        p { font-size: 0.85rem; color: #999; margin: 0; }
        .spinner {
          margin-top: 20px;
          width: 32px; height: 32px;
          border: 3px solid #333;
          border-top-color: #2F5496;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      </style>
    </head>
    <body>
      <div class="icon">⛏️</div>
      <h1>Conciliación Geotécnica</h1>
      <p>${message}</p>
      <div class="spinner"></div>
    </body>
    </html>
  `));
  splash.setMenuBarVisibility(false);
  return splash;
}

/**
 * Close the splash window.
 * @param {BrowserWindow|null} splash
 */
function closeSplash(splash) {
  if (splash && !splash.isDestroyed()) {
    splash.close();
  }
}

module.exports = { showSplash, closeSplash };
