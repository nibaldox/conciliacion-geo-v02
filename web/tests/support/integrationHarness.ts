import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import path from 'node:path';

/**
 * V6-02 — Hermetic launcher for the Python integration harness.
 *
 * `tests/support/frontend_api_integration_harness.py` is executed via
 * `uv run` from the repository root. The previous test inherited
 * `process.env` verbatim, which coupled the test to:
 *
 *   * global uv caches (e.g. `/root/.cache/uv`) that may be unwritable
 *     in CI or locked-down developer shells — `uv run` aborts with
 *     ``Failed to initialize cache`` before Python starts;
 *   * inherited HTTP/HTTPS/ALL proxy variables that may reroute the
 *     Starlette TestClient transport when httpx resolves the URL;
 *   * vitest's default 5 s test timeout, which the cold-start `uv run`
 *     frequently exceeds.
 *
 * This helper fixes all three:
 *
 *   1. Creates a per-call writable ``UV_CACHE_DIR`` under the OS temp
 *      dir and removes it in a ``finally`` block.
 *   2. Builds a clean env from ``process.env`` with every proxy variable
 *      stripped (both upper- and lower-case) and ``NO_PROXY=*`` set so
 *      httpx never attempts an outbound proxy connection.
 *   3. Spawns with an explicit ``timeout`` (default 60 s) well above
 *      the measured ~2 s warm-start and ~5-7 s cold-start; the caller
 *      may override via ``opts.timeoutMs``.
 *
 * The return value mirrors ``spawnSync``'s shape plus a ``timedOut``
 * flag so callers can render precise diagnostics.
 */

const PROXY_VARS = [
  'HTTP_PROXY',
  'HTTPS_PROXY',
  'ALL_PROXY',
  'http_proxy',
  'https_proxy',
  'all_proxy',
] as const;

const REPO_ROOT = path.resolve(process.cwd(), '..');

export interface IntegrationHarnessInput {
  fields: Record<string, unknown>;
  csv: string;
}

export interface IntegrationHarnessResult {
  status: number | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
  signal: NodeJS.Signals | null;
  cacheDir: string;
}

export interface IntegrationHarnessOptions {
  /** Hard kill timeout for the subprocess, in milliseconds.
   * Default: 60_000 (well above the ~7 s cold-start observed in CI). */
  timeoutMs?: number;
}

/** Measured cold-start of `uv run python ... harness.py` + import FastAPI
 *  + init_db + 2 HTTP round-trips is ~5-7 s on the audit host. We add
 *  a generous 10x margin and expose the constant so callers can reason
 *  about the chosen value. */
export const DEFAULT_HARNESS_TIMEOUT_MS = 60_000;

export function runIntegrationHarness(
  input: IntegrationHarnessInput,
  opts: IntegrationHarnessOptions = {},
): IntegrationHarnessResult {
  const timeoutMs = opts.timeoutMs ?? DEFAULT_HARNESS_TIMEOUT_MS;
  const cacheDir = mkdtempSync(join(tmpdir(), 'blast-uv-cache-'));

  const env: NodeJS.ProcessEnv = { ...process.env };
  for (const key of PROXY_VARS) delete env[key];
  env['UV_CACHE_DIR'] = cacheDir;
  env['NO_PROXY'] = '*';
  env['no_proxy'] = '*';

  try {
    const result = spawnSync(
      'uv',
      ['run', 'python', 'tests/support/frontend_api_integration_harness.py'],
      {
        cwd: REPO_ROOT,
        env,
        input: JSON.stringify(input),
        encoding: 'utf8',
        timeout: timeoutMs,
      },
    );
    return {
      status: result.status,
      stdout: result.stdout ?? '',
      stderr: result.stderr ?? '',
      timedOut: result.signal === 'SIGTERM',
      signal: result.signal,
      cacheDir,
    };
  } finally {
    rmSync(cacheDir, { recursive: true, force: true });
  }
}
