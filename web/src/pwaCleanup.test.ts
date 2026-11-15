import { afterEach, describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { purgeLegacyApiCache } from './pwaCleanup';

afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); });
describe('legacy API cache migration', () => {
  it('unregisters workers and blocks mounting for reload', async () => {
    const unregister = vi.fn().mockResolvedValue(true), reload = vi.fn();
    vi.stubGlobal('caches', { has: vi.fn().mockResolvedValue(true), delete: vi.fn().mockResolvedValue(true) });
    vi.stubGlobal('navigator', { serviceWorker: { getRegistrations: vi.fn().mockResolvedValue([{ unregister }]) } });
    expect(await purgeLegacyApiCache(reload)).toBe(true);
    expect(unregister).toHaveBeenCalled();
    expect(reload).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem('conciliacion.swMigrated')).toBe('1');
  });
  it('does not reload twice when the cache reappears', async () => {
    sessionStorage.setItem('conciliacion.swMigrated', '1');
    const remove = vi.fn().mockResolvedValue(true), reload = vi.fn();
    vi.stubGlobal('caches', { has: vi.fn().mockResolvedValue(true), delete: remove });
    expect(await purgeLegacyApiCache(reload)).toBe(false);
    expect(remove).toHaveBeenCalledWith('api-cache');
    expect(reload).not.toHaveBeenCalled();
  });
  it('continues when caches are unavailable', async () => {
    vi.stubGlobal('caches', undefined);
    expect(await purgeLegacyApiCache()).toBe(false);
  });
  it('continues on rejection', async () => {
    vi.stubGlobal('caches', { has: vi.fn().mockRejectedValue(new Error('denied')) });
    expect(await purgeLegacyApiCache()).toBe(false);
  });
  it('blocks mount and session recovery until migration completes', () => {
    const main = readFileSync('src/main.tsx', 'utf8');
    expect(main).toMatch(/if\s*\(await purgeLegacyApiCache\(\)\)\s*return/);
    expect(main.indexOf('await purgeLegacyApiCache()', main.indexOf('async function mountApp'))).toBeLessThan(main.indexOf('await restoreSessionFromHash()'));
  });
  it('does not configure API runtime caching and excludes API navigation fallback', () => {
    const config = readFileSync('vite.config.ts', 'utf8');
    expect(config).not.toContain("cacheName: 'api-cache'");
    const line = config.split('\n').find(line => line.includes('navigateFallbackDenylist'))!;
    expect(line).toContain(String.raw`/\/api\//`);
    const pattern = /\/api\//;
    expect(pattern.test('/api/v1/session')).toBe(true);
    expect(pattern.test('/conciliacion-geo-v02/api/v1/session')).toBe(true);
  });
});
