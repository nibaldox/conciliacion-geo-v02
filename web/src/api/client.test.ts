import { describe, it, expect } from 'vitest';
import { resolveApiBaseUrl } from './client.ts';

describe('resolveApiBaseUrl', () => {
  it('returns the env value as-is when set (regression: Electron build sets VITE_API_URL=/api/v1)', () => {
    // Before the fix, the code did `${VITE_API_URL}/api/v1`, which produced
    // "/api/v1/api/v1" and caused uploads to return 404/405.
    expect(resolveApiBaseUrl('/api/v1')).toBe('/api/v1');
  });

  it('falls back to /api/v1 when env value is undefined', () => {
    expect(resolveApiBaseUrl(undefined)).toBe('/api/v1');
  });

  it('falls back to /api/v1 when env value is the empty string', () => {
    expect(resolveApiBaseUrl('')).toBe('/api/v1');
  });

  it('falls back to /api/v1 when env value is whitespace only', () => {
    expect(resolveApiBaseUrl('   ')).toBe('/api/v1');
  });

  it('preserves an absolute URL (Render deploy case)', () => {
    expect(
      resolveApiBaseUrl('https://conciliacion-api.onrender.com/api/v1'),
    ).toBe('https://conciliacion-api.onrender.com/api/v1');
  });

  it('uses a custom fallback when provided', () => {
    expect(resolveApiBaseUrl(undefined, '/custom/v2')).toBe('/custom/v2');
  });
});
