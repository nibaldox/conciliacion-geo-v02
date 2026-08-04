import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

/* V6-02 — Hermeticidad del spawn del subproceso `uv run`.
 *
 * El test full-stack actual en `blast.fullstack.test.tsx` lanza
 * `uv run python tests/support/frontend_api_integration_harness.py`
 * heredando `process.env` sin filtrar. Eso acopla la prueba a:
 *
 *   1. caches globales de uv (p.ej. `/root/.cache/uv`) que en CI o en
 *      entornos restringidos pueden ser ilegibles/no escribibles —
 *      `uv run` aborta con exit code 2 antes de ejecutar Python.
 *   2. variables de proxy heredadas del shell del desarrollador
 *      (HTTP_PROXY / HTTPS_PROXY / ALL_PROXY) que pueden romper el
 *      TestClient httpx en configuraciones que no son in-process ASGI.
 *   3. timeout por defecto de vitest (5 s) — el arranque en frío del
 *      subproceso (`uv resolve` + import FastAPI + init_db) supera
 *      habitualmente los 5 s, provocando ``Timed out`` espurio.
 *
 * Estos tests reproducen los tres escenarios adversariales y exigen que
 * el subproceso siga retornando exit 0. La corrección (V6-02) extrae
 * un helper que crea un ``UV_CACHE_DIR`` temporal escribible, neutraliza
 * proxies para el subproceso, fija un timeout amplio documentado y
 * limpia el directorio en ``finally``.
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
];

const HARNESS_ARGS = [
  'run',
  'python',
  'tests/support/frontend_api_integration_harness.py',
];

const MINIMAL_PAYLOAD = JSON.stringify({
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
});

describe('fullstack integration subprocess hermeticity (V6-02)', () => {
  const saved: Record<string, string | undefined> = {};

  beforeEachSaveEnv();

  afterEach(() => {
    for (const key of PROXY_VARS) {
      const original = saved[key];
      if (original === undefined) delete process.env[key];
      else process.env[key] = original;
    }
  });

  it('succeeds when UV_CACHE_DIR points to an unwritable path', () => {
    process.env.UV_CACHE_DIR = '/nonexistent-uv-cache-dir/probably';
    const r = spawnSync('uv', HARNESS_ARGS, {
      cwd: path.resolve(process.cwd(), '..'),
      env: process.env,
      input: MINIMAL_PAYLOAD,
      encoding: 'utf8',
    });
    expect(r.status, r.stderr || r.stdout).toBe(0);
    expect(JSON.parse(r.stdout).status_code).toBe(200);
  });

  it('succeeds when SOCKS proxies are set to an invalid host', () => {
    process.env.HTTP_PROXY = 'socks5://invalid.invalid:9999';
    process.env.HTTPS_PROXY = 'socks5://invalid.invalid:9999';
    process.env.ALL_PROXY = 'socks5://invalid.invalid:9999';
    const r = spawnSync('uv', HARNESS_ARGS, {
      cwd: path.resolve(process.cwd(), '..'),
      env: process.env,
      input: MINIMAL_PAYLOAD,
      encoding: 'utf8',
    });
    expect(r.status, r.stderr || r.stdout).toBe(0);
    expect(JSON.parse(r.stdout).status_code).toBe(200);
  });

  it('succeeds with both unwritable cache and invalid SOCKS proxies', () => {
    process.env.UV_CACHE_DIR = '/nonexistent-uv-cache-dir/probably';
    process.env.HTTP_PROXY = 'socks5://invalid.invalid:9999';
    process.env.HTTPS_PROXY = 'socks5://invalid.invalid:9999';
    process.env.ALL_PROXY = 'socks5://invalid.invalid:9999';
    const r = spawnSync('uv', HARNESS_ARGS, {
      cwd: path.resolve(process.cwd(), '..'),
      env: process.env,
      input: MINIMAL_PAYLOAD,
      encoding: 'utf8',
    });
    expect(r.status, r.stderr || r.stdout).toBe(0);
    expect(JSON.parse(r.stdout).status_code).toBe(200);
  });

  function beforeEachSaveEnv() {
    for (const key of PROXY_VARS) {
      saved[key] = process.env[key];
    }
  }
});
