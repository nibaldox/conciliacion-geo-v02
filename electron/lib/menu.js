const { Menu, app, BrowserWindow, dialog, shell } = require('electron');

/**
 * Build the native application menu.
 * Adds File > Open STL/DXF shortcuts and Help > About.
 *
 * @param {BrowserWindow} mainWindow - the main app window
 * @returns {Menu}
 */
function buildAppMenu(mainWindow) {
  const isMac = process.platform === 'darwin';
  const template = [
    ...(isMac ? [{
      label: app.name,
      submenu: [
        { role: 'about' },
        { type: 'separator' },
        { role: 'services' },
        { type: 'separator' },
        { role: 'hide' },
        { role: 'hideOthers' },
        { role: 'unhide' },
        { type: 'separator' },
        { role: 'quit' },
      ],
    }] : []),
    {
      label: 'Archivo',
      submenu: [
        {
          label: 'Cargar superficie de diseño (STL/DXF)...',
          accelerator: 'CmdOrCtrl+O',
          click: async () => {
            const result = await dialog.showOpenDialog(mainWindow, {
              title: 'Cargar superficie de diseño',
              filters: [
                { name: 'Superficies 3D', extensions: ['stl', 'obj', 'ply', 'dxf'] },
                { name: 'Todos los archivos', extensions: ['*'] },
              ],
              properties: ['openFile'],
            });
            if (!result.canceled && result.filePaths[0]) {
              // The web app needs to handle this. We can either:
              // 1. Send an IPC event to the renderer
              // 2. Open the file URL directly: file:///path/to/file.dxf
              // 3. Just log it for now
              mainWindow.webContents.send('file:open-design', result.filePaths[0]);
            }
          },
        },
        {
          label: 'Cargar superficie topográfica (STL/DXF)...',
          accelerator: 'CmdOrCtrl+Shift+O',
          click: async () => {
            const result = await dialog.showOpenDialog(mainWindow, {
              title: 'Cargar superficie topográfica',
              filters: [
                { name: 'Superficies 3D', extensions: ['stl', 'obj', 'ply', 'dxf'] },
                { name: 'Todos los archivos', extensions: ['*'] },
              ],
              properties: ['openFile'],
            });
            if (!result.canceled && result.filePaths[0]) {
              mainWindow.webContents.send('file:open-topo', result.filePaths[0]);
            }
          },
        },
        { type: 'separator' },
        isMac ? { role: 'close' } : { role: 'quit' },
      ],
    },
    {
      label: 'Editar',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
      ],
    },
    {
      label: 'Ver',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'Ayuda',
      submenu: [
        {
          label: 'Acerca de Conciliación Geotécnica',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'Acerca de',
              message: 'Conciliación Geotécnica v' + app.getVersion(),
              detail: 'Herramienta de conciliación geotécnica para taludes en minería.\nElectron: ' + process.versions.electron + '\nNode: ' + process.versions.node,
            });
          },
        },
        {
          label: 'Documentación',
          click: () => {
            shell.openExternal('https://github.com/nibaldox/conciliacion-geo-v02');
          },
        },
      ],
    },
  ];
  return Menu.buildFromTemplate(template);
}

/**
 * Install the menu as the application menu.
 * @param {BrowserWindow} mainWindow
 */
function installAppMenu(mainWindow) {
  const menu = buildAppMenu(mainWindow);
  Menu.setApplicationMenu(menu);
}

module.exports = { buildAppMenu, installAppMenu };
