const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');

/**
 * Minimal Electron main-process stub.
 * The real BrowserWindow and dialog APIs require a full Electron runtime,
 * so we inject a fake `electron` module into the require cache before
 * loading the module under test. This lets `node --test` run the unit
 * tests without launching a full Electron app.
 */

class FakeBrowserWindow {
  constructor(options) {
    this.options = options;
    this._destroyed = false;
  }

  loadURL() {
    return Promise.resolve();
  }

  setMenuBarVisibility() {}

  isDestroyed() {
    return this._destroyed;
  }

  close() {
    this._destroyed = true;
  }
}

function stubElectron() {
  const electronPath = require.resolve('electron');
  // Replace the cached electron export with a stub that only exposes
  // the BrowserWindow constructor used by splash.js.
  require.cache[electronPath] = {
    id: electronPath,
    filename: electronPath,
    loaded: true,
    exports: { BrowserWindow: FakeBrowserWindow },
  };
}

stubElectron();

const { showSplash, closeSplash } = require('./splash');

const fakeIcon = '/fake/path/icon.png';

test('showSplash returns a BrowserWindow-like object with the expected API', () => {
  const splash = showSplash({ iconPath: fakeIcon });
  assert.ok(splash instanceof FakeBrowserWindow, 'showSplash should return a FakeBrowserWindow instance');
  assert.strictEqual(typeof splash.loadURL, 'function', 'splash should expose loadURL');
  assert.strictEqual(typeof splash.setMenuBarVisibility, 'function', 'splash should expose setMenuBarVisibility');
  assert.strictEqual(typeof splash.isDestroyed, 'function', 'splash should expose isDestroyed');
  assert.strictEqual(typeof splash.close, 'function', 'splash should expose close');
  assert.strictEqual(splash.isDestroyed(), false);
  closeSplash(splash);
});

test('showSplash accepts a custom message', () => {
  const splash = showSplash({ iconPath: fakeIcon, message: 'Custom loading message' });
  assert.ok(splash instanceof FakeBrowserWindow);
  assert.strictEqual(splash.isDestroyed(), false);
  closeSplash(splash);
});

test('closeSplash handles null gracefully', () => {
  assert.doesNotThrow(() => closeSplash(null));
});

test('closeSplash handles an already destroyed window gracefully', () => {
  const splash = showSplash({ iconPath: fakeIcon });
  splash.close();
  assert.strictEqual(splash.isDestroyed(), true);
  assert.doesNotThrow(() => closeSplash(splash));
});
