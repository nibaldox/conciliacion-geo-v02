import { afterEach, describe, expect, it } from 'vitest';
import {
  DEFAULT_HARNESS_TIMEOUT_MS,
  runIntegrationHarness,
} from './support/integrationHarness';

/* V6-02 — Hermeticidad del spawn del subproceso `uv run`.
 *
 * El helper ``runIntegrationHarness`` aísla el subproceso en tres ejes:
 *
 *   1. Crea un ``UV_CACHE_DIR`` temporal escribible y lo limpia en
 *      ``finally``. Sin esto, ``uv run`` aborta con exit code 2 si la
 *      cache global heredada (p.ej. ``/root/.cache/uv``) es ilegible o
 *      no escribible — el síntoma observado por la auditoría V5 fue
 *      ``1 failed, 370 passed`` sin diagnostico claro.
 *   2. Construye el entorno del subproceso desde ``process.env`` pero
 *      eliminando HTTP_PROXY / HTTPS_PROXY / ALL_PROXY (ambas
 *      mayúsculas/minúsculas) y fijando ``NO_PROXY=*``. El TestClient
 *      in-process normalmente no enruta por proxy, pero el contrato
 *      queda como guardia para configuraciones no in-process.
 *   3. Spawnea con timeout explícito de 60 s (DEFAULT_HARNESS_TIMEOUT_MS),
 *      > 10x el arranque en frío medido (~5-7 s).
 *
 * Estas pruebas verifican que el helper sigue entregando exit 0 incluso
 * cuando el proceso padre (vitest) tiene los tres vectores adversariales
 * activos en su ``process.env``.
 */

const PROXY_VARS = [
  'HTTP_PROXY',
  'HTTPS_PROXY',
  'ALL_PROXY',
  'http_proxy',
  'https_proxy',
  'all_proxy',
  'UV_CACHE_DIR',
  'NO_PROXY',
  'no_proxy',
] as const;

const VALID_PAYLOAD = {
  fields: {
    geometry_configuration_version: '2.0',
    geometry_user_confirmed: true,
    inclination_source_column: 'Inclinacion_real',
    inclination_convention: 'FROM_VERTICAL',
    inclination_sign_convention: 'ABSOLUTE_VALUE',
    inclination_unit: 'DEGREES',
    inclination_source_rule: '',
    azimuth_source_column: 'Azimuth_real',
    azimuth_convention: 'CLOCKWISE_FROM_NORTH',
    azimuth_unit: 'RADIANS',
  },
  csv: [
    'Latitud_Geo,Longitud_Geo,Nombre_Banco,Inclinacion_real,Azimuth_real,longitud_real',
    '1000.0,2000.0,4000,15.0,1.5707963267948966,12.0',
  ].join('\n'),
};

describe('fullstack integration subprocess hermeticity (V6-02)', () => {
  const saved: Record<string, string | undefined> = {};
  beforeAllSaveEnv(saved);

  afterEach(() => {
    for (const key of PROXY_VARS) {
      const original = saved[key];
      if (original === undefined) delete process.env[key];
      else process.env[key] = original;
    }
  });

  it('default timeout is well above the measured cold start', () => {
    // Cold start of `uv run python ... harness.py` measured ~5-7 s on
    // the audit host. 60 s gives > 10x margin without being so large
    // that a real hang goes unnoticed.
    expect(DEFAULT_HARNESS_TIMEOUT_MS).toBeGreaterThanOrEqual(30_000);
    expect(DEFAULT_HARNESS_TIMEOUT_MS).toBeLessThanOrEqual(120_000);
  });

  it('succeeds when UV_CACHE_DIR points to an unwritable path', () => {
    process.env.UV_CACHE_DIR = '/nonexistent-uv-cache-dir/probably';
    const r = runIntegrationHarness(VALID_PAYLOAD);
    expect(r.timedOut, 'subprocess timed out').toBe(false);
    expect(r.status, r.stderr || r.stdout).toBe(0);
    expect(JSON.parse(r.stdout).status_code).toBe(200);
    // The helper MUST have cleaned up its own temp cache dir.
    expect(r.cacheDir).not.toBe('/nonexistent-uv-cache-dir/probably');
  });

  it('succeeds when SOCKS proxies are set to an invalid host', () => {
    process.env.HTTP_PROXY = 'socks5://invalid.invalid:9999';
    process.env.HTTPS_PROXY = 'socks5://invalid.invalid:9999';
    process.env.ALL_PROXY = 'socks5://invalid.invalid:9999';
    const r = runIntegrationHarness(VALID_PAYLOAD);
    expect(r.timedOut, 'subprocess timed out').toBe(false);
    expect(r.status, r.stderr || r.stdout).toBe(0);
    expect(JSON.parse(r.stdout).status_code).toBe(200);
  });

  it('succeeds with both unwritable cache and invalid SOCKS proxies', () => {
    process.env.UV_CACHE_DIR = '/nonexistent-uv-cache-dir/probably';
    process.env.HTTP_PROXY = 'socks5://invalid.invalid:9999';
    process.env.HTTPS_PROXY = 'socks5://invalid.invalid:9999';
    process.env.ALL_PROXY = 'socks5://invalid.invalid:9999';
    const r = runIntegrationHarness(VALID_PAYLOAD);
    expect(r.timedOut, 'subprocess timed out').toBe(false);
    expect(r.status, r.stderr || r.stdout).toBe(0);
    expect(JSON.parse(r.stdout).status_code).toBe(200);
  });
});

function beforeAllSaveEnv(store: Record<string, string | undefined>) {
  for (const key of PROXY_VARS) {
    store[key] = process.env[key];
  }
}
