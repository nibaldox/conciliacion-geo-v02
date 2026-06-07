const http = require('node:http');

/**
 * Poll the FastAPI health endpoint until it returns 200 or timeout.
 * @param {number} port - localhost port where the sidecar is listening
 * @param {number} timeoutMs - total timeout in ms
 * @param {number} intervalMs - poll interval in ms
 * @returns {Promise<void>} resolves when health returns 200
 * @throws {Error} if the timeout is reached
 */
function waitForHealth(port, timeoutMs = 10000, intervalMs = 200) {
  const deadline = Date.now() + timeoutMs;

  function attempt() {
    return new Promise((resolve, reject) => {
      const req = http.request(
        { host: '127.0.0.1', port, path: '/api/v1/health', method: 'GET', timeout: 1000 },
        (res) => {
          if (res.statusCode === 200) {
            res.resume();
            resolve();
          } else {
            res.resume();
            reject(new Error(`Health check returned ${res.statusCode}`));
          }
        }
      );
      req.on('error', reject);
      req.on('timeout', () => {
        req.destroy();
        reject(new Error('Health check request timed out'));
      });
      req.end();
    });
  }

  return new Promise((resolve, reject) => {
    function tick() {
      const remaining = deadline - Date.now();
      if (remaining <= 0) {
        return reject(new Error(`waitForHealth timed out after ${timeoutMs}ms`));
      }
      attempt().then(resolve, () => {
        setTimeout(tick, Math.min(intervalMs, remaining));
      });
    }
    tick();
  });
}

module.exports = { waitForHealth };
