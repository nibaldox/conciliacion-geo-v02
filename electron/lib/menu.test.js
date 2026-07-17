const test = require('node:test');
const assert = require('node:assert');

/**
 * Menu tests run inside an Electron main-process context in production.
 * In the unit-test runner (`node --test`) we inject a fake `electron`
 * module so Menu.buildFromTemplate and the app menu can be exercised
 * without a real native UI.
 */

class FakeMenu {
  constructor(items) {
    this.items = items;
  }

  static buildFromTemplate(template) {
    const items = template.map((item) => {
      if (Array.isArray(item.submenu)) {
        return { ...item, submenu: new FakeMenu(item.submenu) };
      }
      return item;
    });
    return new FakeMenu(items);
  }
}

let applicationMenu = null;
FakeMenu.setApplicationMenu = (menu) => {
  applicationMenu = menu;
};

FakeMenu.getApplicationMenu = () => applicationMenu;

function stubElectron() {
  const electronPath = require.resolve('electron');
  const fakeElectron = {
    Menu: FakeMenu,
    app: {
      name: 'Conciliación Geotécnica',
      getVersion: () => '0.1.1',
    },
    BrowserWindow: class FakeBrowserWindow {},
    dialog: {},
    shell: {},
  };
  require.cache[electronPath] = {
    id: electronPath,
    filename: electronPath,
    loaded: true,
    exports: fakeElectron,
  };
  return fakeElectron;
}

stubElectron();

const { buildAppMenu, installAppMenu } = require('./menu');

function getLabels(menu) {
  return menu.items.map((item) => item.label);
}

function findItem(menu, label) {
  return menu.items.find((item) => item.label === label);
}

test('buildAppMenu returns a Menu with the expected top-level labels', () => {
  const fakeWindow = { webContents: { send: () => {} } };
  const menu = buildAppMenu(fakeWindow);
  assert.ok(menu instanceof FakeMenu, 'buildAppMenu should return a FakeMenu instance');

  const labels = getLabels(menu);
  assert.ok(labels.includes('Archivo'), 'top-level menu should contain Archivo');
  assert.ok(labels.includes('Editar'), 'top-level menu should contain Editar');
  assert.ok(labels.includes('Ver'), 'top-level menu should contain Ver');
  assert.ok(labels.includes('Ayuda'), 'top-level menu should contain Ayuda');
});

test('Archivo menu contains the design and topo surface open items', () => {
  const fakeWindow = { webContents: { send: () => {} } };
  const menu = buildAppMenu(fakeWindow);
  const archivo = findItem(menu, 'Archivo');
  assert.ok(archivo, 'Archivo menu should exist');

  const subLabels = archivo.submenu.items.map((item) => item.label);
  assert.ok(subLabels.includes('Cargar superficie de diseño (STL/DXF)...'));
  assert.ok(subLabels.includes('Cargar superficie topográfica (STL/DXF)...'));
});

test('Ayuda menu contains About and Documentation items', () => {
  const fakeWindow = { webContents: { send: () => {} } };
  const menu = buildAppMenu(fakeWindow);
  const ayuda = findItem(menu, 'Ayuda');
  assert.ok(ayuda, 'Ayuda menu should exist');

  const subLabels = ayuda.submenu.items.map((item) => item.label);
  assert.ok(subLabels.includes('Acerca de Conciliación Geotécnica'));
  assert.ok(subLabels.includes('Documentación'));
});

test('installAppMenu sets the built menu as the application menu', () => {
  const fakeWindow = { webContents: { send: () => {} } };
  installAppMenu(fakeWindow);
  const current = FakeMenu.getApplicationMenu();
  assert.ok(current, 'Application menu should be set');
  assert.ok(current.items.length > 0, 'Application menu should have items');
});
