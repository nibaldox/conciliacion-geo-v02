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
  fs.mkdirSync(path.dirname(binPath), { recursive: true });
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
  assert.strictEqual(getSidecarPath('/fake/resources'), path.join('/fake/resources', 'conciliacion-api', expected));
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

test('spawnSidecar sovereignty pins override degrading parent env', { skip: isWindows }, async () => {
  const dir = makeTempDir();
  const logFile = path.join(dir, 'pins.log');
  const keys = ['CONCILIACION_AI_CHAT_ENABLED', 'CONCILIACION_AI_LOCAL_ONLY', 'CONCILIACION_WORKERS'];
  createFakeBinary(dir, `
for (const key of ${JSON.stringify(keys)}) {
  console.log(key + '=' + process.env[key]);
}
`);
  const previous = Object.fromEntries(keys.map((k) => [k, process.env[k]]));
  process.env.CONCILIACION_AI_CHAT_ENABLED = 'false';
  process.env.CONCILIACION_AI_LOCAL_ONLY = '0';
  process.env.CONCILIACION_WORKERS = '8';
  try {
    const proc = spawnSidecar({ resourcesPath: dir, logFile });

    await new Promise((resolve) => setTimeout(resolve, 300));
    proc.kill();
    await waitForExit(proc);

    const contents = await waitForLogContents(logFile, [
      'CONCILIACION_AI_CHAT_ENABLED=true',
      'CONCILIACION_AI_LOCAL_ONLY=1',
      'CONCILIACION_WORKERS=1',
    ]);
    assert.ok(contents.includes('CONCILIACION_AI_CHAT_ENABLED=true'), 'pin CONCILIACION_AI_CHAT_ENABLED=true must win after both spreads');
    assert.ok(contents.includes('CONCILIACION_AI_LOCAL_ONLY=1'), 'pin CONCILIACION_AI_LOCAL_ONLY=1 must win after both spreads');
    assert.ok(contents.includes('CONCILIACION_WORKERS=1'), 'pin CONCILIACION_WORKERS=1 must win after both spreads');
  } finally {
    for (const [k, v] of Object.entries(previous)) {
      if (v === undefined) {
        delete process.env[k];
      } else {
        process.env[k] = v;
      }
    }
  }
});

test('spawnSidecar preserves inherited CONCILIACION_LMSTUDIO_BASE_URL', { skip: isWindows }, async () => {
  const dir = makeTempDir();
  const logFile = path.join(dir, 'lmstudio.log');
  createFakeBinary(dir, `console.log('LMSTUDIO_BASE_URL=' + process.env.CONCILIACION_LMSTUDIO_BASE_URL);`);
  const previous = process.env.CONCILIACION_LMSTUDIO_BASE_URL;
  process.env.CONCILIACION_LMSTUDIO_BASE_URL = 'http://10.0.0.5:1234/v1';
  try {
    const proc = spawnSidecar({ resourcesPath: dir, logFile });

    await new Promise((resolve) => setTimeout(resolve, 300));
    proc.kill();
    await waitForExit(proc);

    const contents = await waitForLogContents(logFile, ['LMSTUDIO_BASE_URL=http://10.0.0.5:1234/v1']);
    assert.ok(contents.includes('LMSTUDIO_BASE_URL=http://10.0.0.5:1234/v1'), 'inherited LM Studio URL must pass through to spawned env');
  } finally {
    if (previous === undefined) {
      delete process.env.CONCILIACION_LMSTUDIO_BASE_URL;
    } else {
      process.env.CONCILIACION_LMSTUDIO_BASE_URL = previous;
    }
  }
});

test('spawnSidecar defaults MALLOC_ARENA_MAX to 2 when parent does not set it', { skip: isWindows }, async () => {
  const dir = makeTempDir();
  const logFile = path.join(dir, 'malloc.log');
  createFakeBinary(dir, `console.log('MALLOC_ARENA_MAX=' + process.env.MALLOC_ARENA_MAX);`);
  const previous = process.env.MALLOC_ARENA_MAX;
  delete process.env.MALLOC_ARENA_MAX;
  try {
    const proc = spawnSidecar({ resourcesPath: dir, logFile });

    await new Promise((resolve) => setTimeout(resolve, 300));
    proc.kill();
    await waitForExit(proc);

    const contents = await waitForLogContents(logFile, ['MALLOC_ARENA_MAX=2']);
    assert.ok(contents.includes('MALLOC_ARENA_MAX=2'), 'default MALLOC_ARENA_MAX=2 must apply without parent override');
  } finally {
    if (previous !== undefined) {
      process.env.MALLOC_ARENA_MAX = previous;
    }
  }
});
