const test = require('node:test');
const assert = require('node:assert');
const net = require('node:net');
const { isPortInUse, findFreePort } = require('./port');

test('isPortInUse returns false for a free port', async () => {
  const free = await findFreePort();
  const inUse = await isPortInUse(free);
  assert.strictEqual(inUse, false);
});

test('isPortInUse returns true for a busy port', async () => {
  const port = await findFreePort();
  const server = net.createServer();
  await new Promise((resolve) => server.listen(port, '127.0.0.1', resolve));
  try {
    const inUse = await isPortInUse(port);
    assert.strictEqual(inUse, true);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('findFreePort returns a port in the valid range', async () => {
  const port = await findFreePort();
  assert.ok(port >= 1024 && port <= 65535, `Port ${port} out of range`);
});
