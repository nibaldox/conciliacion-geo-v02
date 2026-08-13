import { describe, it, expect } from 'vitest';
import { resolveApiBaseUrl, normalizeJsonResponse, gunzipToString } from './client.ts';

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

describe('gzip response normalization (V6-03)', () => {
  // Compress with the native web CompressionStream (no node dependency).
  async function gzipText(text: string): Promise<Uint8Array> {
    const stream = new CompressionStream('gzip');
    const writer = stream.writable.getWriter();
    await writer.write(new TextEncoder().encode(text));
    await writer.close();
    const reader = stream.readable.getReader();
    const chunks: Uint8Array[] = [];
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value as Uint8Array);
    }
    const len = chunks.reduce((n, c) => n + c.length, 0);
    const out = new Uint8Array(len);
    let off = 0;
    for (const c of chunks) {
      out.set(c, off);
      off += c.length;
    }
    return out;
  }

  it('gunzipToString round-trips gzip bytes to the original UTF-8 string', async () => {
    const original = 'héllo μγ — simulation';
    const bytes = await gzipText(original);
    expect(await gunzipToString(bytes)).toBe(original);
  });

  it('decompresses a gzipped JSON Uint8Array and preserves simulation_id', async () => {
    // Simulates a body that reached the app still compressed (e.g. a service
    // worker forwarded the raw bytes). The panel must NOT receive bytes as a
    // "successful" JSON payload.
    const payload = { simulation_id: 'sim-xyz', values: [1, 2, 3] };
    const compressed = await gzipText(JSON.stringify(payload));
    const out = await normalizeJsonResponse(compressed);
    expect(out).toEqual(payload);
    expect((out as { simulation_id: string }).simulation_id).toBe('sim-xyz');
  });

  it('decompresses a gzipped JSON ArrayBuffer', async () => {
    const payload = { simulation_id: 'sim-abc', ok: true };
    const buffer = (await gzipText(JSON.stringify(payload))).buffer as ArrayBuffer;
    const out = await normalizeJsonResponse(buffer);
    expect(out).toEqual(payload);
  });

  it('passes through an already-parsed object (browser auto-decompress path)', async () => {
    const payload = { simulation_id: 'sim-parsed', values: [9] };
    await expect(normalizeJsonResponse(payload)).resolves.toBe(payload);
  });

  it('passes through a Blob (binary downloads like npz/xlsx)', async () => {
    const blob = new Blob([await gzipText(JSON.stringify({ simulation_id: 'x' }))]);
    await expect(normalizeJsonResponse(blob)).resolves.toBe(blob);
  });

  it('passes through plain (non-gzip) bytes untouched', async () => {
    const plain = new Uint8Array([0x7b, 0x22, 0x61, 0x22, 0x3a, 0x31, 0x7d]); // {"a":1}
    await expect(normalizeJsonResponse(plain)).resolves.toBe(plain);
  });

  it('returns the original value when gzip bytes fail to parse as JSON', async () => {
    // Valid gzip stream wrapping non-JSON text.
    const compressed = await gzipText('not-json');
    await expect(normalizeJsonResponse(compressed)).resolves.toBe(compressed);
  });
});
