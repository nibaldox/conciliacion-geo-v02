import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || '';

let currentSessionId: string | null = null;

export function getSessionId(): string | null {
  return currentSessionId;
}

const client = axios.create({
  baseURL: `${API_BASE}/api/v1`,
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
