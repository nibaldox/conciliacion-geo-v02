const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const { waitForHealth } = require('./health');

function startFakeApi(port, statusCode = 200) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      if (req.url === '/api/v1/health') {
        res.writeHead(statusCode, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'ok' }));
      } else {
        res.writeHead(404);
        res.end();
      }
    });
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

test('waitForHealth resolves when API returns 200', async () => {
  const server = await startFakeApi(0, 200);
  const port = server.address().port;
  try {
    await waitForHealth(port, 2000, 50);
    assert.ok(true, 'waitForHealth resolved');
  } finally {
    await new Promise((r) => server.close(r));
  }
});

test('waitForHealth rejects when API never returns 200', async () => {
  const server = await startFakeApi(0, 500);
  const port = server.address().port;
  try {
    await assert.rejects(
      () => waitForHealth(port, 500, 50),
      /timed out/i
    );
  } finally {
    await new Promise((r) => server.close(r));
  }
});
