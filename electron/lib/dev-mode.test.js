const test = require('node:test');
const assert = require('node:assert');
const { isDevMode, getDevUrl } = require('./dev-mode');

test('isDevMode returns true when CONCILIACION_ELECTRON_DEV=1', () => {
  const original = process.env.CONCILIACION_ELECTRON_DEV;
  process.env.CONCILIACION_ELECTRON_DEV = '1';
  try {
    assert.strictEqual(isDevMode(), true);
  } finally {
    process.env.CONCILIACION_ELECTRON_DEV = original;
  }
});

test('isDevMode returns false for any other value', () => {
  const original = process.env.CONCILIACION_ELECTRON_DEV;
  for (const value of ['0', '', 'true', undefined, 'yes']) {
    process.env.CONCILIACION_ELECTRON_DEV = value;
    assert.strictEqual(isDevMode(), false, `expected false for ${value}`);
  }
  process.env.CONCILIACION_ELECTRON_DEV = original;
});

test('getDevUrl returns CONCILIACION_DEV_URL when set', () => {
  const original = process.env.CONCILIACION_DEV_URL;
  process.env.CONCILIACION_DEV_URL = 'http://localhost:3000';
  try {
    assert.strictEqual(getDevUrl(), 'http://localhost:3000');
  } finally {
    process.env.CONCILIACION_DEV_URL = original;
  }
});

test('getDevUrl returns default Vite URL when not set', () => {
  const original = process.env.CONCILIACION_DEV_URL;
  delete process.env.CONCILIACION_DEV_URL;
  try {
    assert.strictEqual(getDevUrl(), 'http://localhost:5173');
  } finally {
    process.env.CONCILIACION_DEV_URL = original;
  }
});
