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

// Store session ID from response
client.interceptors.response.use(
  (response) => {
    const sessionId = response.headers['x-session-id'];
    if (sessionId) {
      currentSessionId = sessionId as string;
    }
    return response;
  },
  (error) => {
    // Preserve session ID even on errors
    const sessionId = error.response?.headers?.['x-session-id'];
    if (sessionId) {
      currentSessionId = sessionId as string;
    }
    return Promise.reject(error);
  }
);

export default client;
