const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { getSidecarPath, spawnSidecar } = require('./spawn-sidecar');

const isWindows = process.platform === 'win32';

/**
 * Create a fake sidecar binary in a temporary directory.
 *
 * On Linux/macOS this is a Node.js script with a shebang so it executes
 * without extra dependencies. On Windows, creating a PE executable on the
 * fly is not practical without external tools, so tests that need a real
 * process are skipped on that platform.
 */
function createFakeBinary(resourcesPath, script) {
  const binPath = getSidecarPath(resourcesPath);
  fs.mkdirSync(resourcesPath, { recursive: true });
  const content = `#!/usr/bin/env node
${script}
`;
  fs.writeFileSync(binPath, content, { mode: 0o755 });
  fs.chmodSync(binPath, 0o755);
  return binPath;
}

function makeTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'spawn-sidecar-test-'));
}

function waitForExit(proc) {
  if (proc.exitCode !== null || proc.signalCode !== null) {
    return Promise.resolve();
  }
  return new Promise((resolve) => proc.once('exit', resolve));
}

function waitForLogContents(logFile, expected, timeoutMs = 2000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    function check() {
      try {
        const contents = fs.readFileSync(logFile, 'utf8');
        if (expected.every((s) => contents.includes(s))) {
          return resolve(contents);
        }
      } catch (err) {
        if (err.code !== 'ENOENT') {
          return reject(err);
        }
      }
      if (Date.now() > deadline) {
        return reject(new Error(`Timed out waiting for log contents in ${logFile}`));
      }
      setTimeout(check, 50);
    }
    check();
  });
}

test('getSidecarPath returns correct name for current platform', () => {
  const expected = process.platform === 'win32' ? 'conciliacion-api.exe' : 'conciliacion-api';
  assert.match(getSidecarPath('/fake/resources'), new RegExp(`${expected}$`));
  assert.ok(getSidecarPath('/fake/resources').endsWith(expected));
});

test('spawnSidecar throws SIDECAR_NOT_FOUND when binary does not exist', () => {
  assert.throws(
    () => spawnSidecar({ resourcesPath: '/nonexistent' }),
    (err) => err.code === 'SIDECAR_NOT_FOUND' && /not found/i.test(err.message)
  );
});

test('spawnSidecar spawns a real process when binary exists', { skip: isWindows }, () => {
  const dir = makeTempDir();
  createFakeBinary(dir, `
console.log('fake server');
setTimeout(() => {}, 1000);
`);
  const proc = spawnSidecar({ resourcesPath: dir });
  try {
    assert.ok(typeof proc.pid === 'number' && proc.pid > 0, 'process.pid should be a positive number');
    assert.strictEqual(proc.killed, false);
  } finally {
    proc.kill();
  }
});

test('spawnSidecar pipes stdio to log file when logFile is provided', { skip: isWindows }, async () => {
  const dir = makeTempDir();
  const logFile = path.join(dir, 'sidecar.log');
  createFakeBinary(dir, `
console.log('stdout-line');
console.error('stderr-line');
`);
  const proc = spawnSidecar({ resourcesPath: dir, logFile });

  await new Promise((resolve) => setTimeout(resolve, 300));
  proc.kill();
  await waitForExit(proc);

  const contents = await waitForLogContents(logFile, ['stdout-line', 'stderr-line']);
  assert.ok(contents.includes('stdout-line'), 'log file should contain stdout');
  assert.ok(contents.includes('stderr-line'), 'log file should contain stderr');
});

test('spawnSidecar merges env vars', { skip: isWindows }, async () => {
  const dir = makeTempDir();
  const logFile = path.join(dir, 'env.log');
  createFakeBinary(dir, `console.log(process.env.TEST_VAR);`);
  const proc = spawnSidecar({
    resourcesPath: dir,
    logFile,
    env: { TEST_VAR: 'hello' },
  });

  await new Promise((resolve) => setTimeout(resolve, 300));
  proc.kill();
  await waitForExit(proc);

  const contents = await waitForLogContents(logFile, ['hello']);
  assert.ok(contents.includes('hello'), 'log file should contain merged env var value');
});
