import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || '';

const client = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  timeout: 120000, // 2 min for heavy processing
  headers: {
    'Content-Type': 'application/json',
  },
});

// Session middleware: inject X-Session-ID
client.interceptors.request.use((config) => {
  const sessionId = localStorage.getItem('session_id');
  if (sessionId) {
    config.headers['X-Session-ID'] = sessionId;
  }
  return config;
});

// Store session ID from response
client.interceptors.response.use(
  (response) => {
    const sessionId = response.headers['x-session-id'];
    if (sessionId) {
      localStorage.setItem('session_id', sessionId as string);
    }
    return response;
  },
  (error) => {
    // Preserve session ID even on errors
    if (error.response?.headers?.['x-session-id']) {
      localStorage.setItem('session_id', error.response.headers['x-session-id']);
    }
    return Promise.reject(error);
  }
);

export default client;
