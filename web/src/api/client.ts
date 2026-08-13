import axios from 'axios';

const FALLBACK_API_BASE = '/api/v1';

let currentSessionId: string | null = null;

export function getSessionId(): string | null {
  return currentSessionId;
}

/**
 * Resolve the API base URL from the build-time env var.
 *
 * IMPORTANT: this function must NOT concatenate the versioned prefix.
 * Callers pass a path that already starts with `/api/v1/...`, so the
 * baseURL must be either the env var (when it already points at the
 * versioned API root) or the fallback `/api/v1`.
 *
 * Bug history: concatenating `${VITE_API_URL}/api/v1` produced
 * `/api/v1/api/v1` in the Electron build (which sets
 * `VITE_API_URL=/api/v1`) and caused the upload endpoint to return 404/405.
 */
export function resolveApiBaseUrl(
  envValue: string | undefined,
  fallback: string = FALLBACK_API_BASE,
): string {
  if (envValue && envValue.trim().length > 0) return envValue;
  return fallback;
}

// ---------------------------------------------------------------------------
// V6-03: gzip response normalization
// ---------------------------------------------------------------------------
//
// The backend serves large simulation payloads with the standard HTTP
// ``Content-Encoding: gzip`` and a semantic ``application/json`` content
// type. Browsers (and therefore Axios in the browser) transparently
// decompress standard Content-Encoding, so in the common path the body is
// already parsed JSON by the time it reaches the app. ``normalizeJsonResponse``
// is a defensive fallback for the edge case where a body still arrives as
// raw gzip bytes (e.g. a service worker forwarding bytes without decoding),
// so the panel never treats binary as a "successful" JSON payload. Binary
// downloads (Blob, e.g. ``fmt=npz``/``fmt=xlsx``) are always passed through.

const GZIP_MAGIC_0 = 0x1f;
const GZIP_MAGIC_1 = 0x8b;

type ByteBuffer = Uint8Array | ArrayBuffer | ArrayBufferView;

function isByteBuffer(data: unknown): data is ByteBuffer {
  if (data instanceof Uint8Array) return true;
  if (data instanceof ArrayBuffer) return true;
  return typeof ArrayBuffer !== 'undefined' && ArrayBuffer.isView(data);
}

function toUint8Array(data: ByteBuffer): Uint8Array {
  if (data instanceof Uint8Array) return data;
  if (data instanceof ArrayBuffer) return new Uint8Array(data);
  return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
}

function looksGzip(bytes: Uint8Array): boolean {
  return bytes.length >= 2 && bytes[0] === GZIP_MAGIC_0 && bytes[1] === GZIP_MAGIC_1;
}

/** Decompress gzip bytes into a UTF-8 string via the standard web
 *  ``DecompressionStream`` (available in browsers and Node ≥ 18). */
export async function gunzipToString(bytes: Uint8Array): Promise<string> {
  const stream = new DecompressionStream('gzip');
  const writer = stream.writable.getWriter();
  await writer.write(bytes);
  await writer.close();
  const reader = stream.readable.getReader();
  const decoder = new TextDecoder('utf-8');
  let out = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    out += decoder.decode(value, { stream: true });
  }
  out += decoder.decode();
  return out;
}

/**
 * Ensure a JSON-semantic response never reaches callers as raw gzip bytes.
 *
 * - Object / null (already parsed JSON, the normal browser path) → returned
 *   unchanged.
 * - Blob (intentional binary downloads) → returned unchanged.
 * - ``Uint8Array`` / ``ArrayBuffer`` starting with the gzip magic bytes →
 *   decompressed with ``DecompressionStream`` and parsed as JSON; if parsing
 *   fails the original value is returned so the caller still sees the bytes.
 */
export async function normalizeJsonResponse(data: unknown): Promise<unknown> {
  // Intentional binary downloads (npz/xlsx) stay untouched.
  if (data instanceof Blob) return data;
  // A body that arrived as raw bytes — decompress if it is gzip, else
  // return unchanged. (Uint8Array/ArrayBuffer are objects, so this MUST
  // be checked before the generic object pass-through below.)
  if (isByteBuffer(data)) {
    const bytes = toUint8Array(data);
    if (looksGzip(bytes)) {
      try {
        return JSON.parse(await gunzipToString(bytes));
      } catch {
        return data;
      }
    }
    return data;
  }
  // Already-parsed JSON (the normal browser auto-decompress path), null,
  // or any non-byte primitive: return unchanged.
  return data;
}

const client = axios.create({
  baseURL: resolveApiBaseUrl(import.meta.env.VITE_API_URL),
  timeout: 120000, // 2 min for heavy processing
  headers: {
    'Content-Type': 'application/json',
  },
});

// Session middleware: inject X-Session-ID
client.interceptors.request.use((config) => {
  if (currentSessionId) {
    config.headers['X-Session-ID'] = currentSessionId;
  }
  return config;
});

// Store session ID from response, and normalize any gzip JSON body so the
// panel never receives binary as a successful JSON payload (V6-03).
client.interceptors.response.use(
  async (response) => {
    const sid = response.headers['x-session-id'];
    if (typeof sid === 'string') {
      currentSessionId = sid;
    }
    if (!(response.data instanceof Blob)) {
      response.data = await normalizeJsonResponse(response.data);
    }
    return response;
  },
  (error) => {
    // Preserve session ID even on errors
    const sid = error.response?.headers?.['x-session-id'];
    if (typeof sid === 'string') {
      currentSessionId = sid;
    }
    return Promise.reject(error);
  }
);

export default client;
