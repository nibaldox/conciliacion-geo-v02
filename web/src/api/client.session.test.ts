import { beforeEach, describe, expect, it } from 'vitest';
import type { AxiosAdapter } from 'axios';
import client, { getSessionId, setSessionId } from './client';

describe('session persistence', () => {
  beforeEach(() => { localStorage.clear(); setSessionId(null); });
  it('persists and removes the session id', () => {
    setSessionId('chosen');
    expect(localStorage.getItem('conciliacion.sessionId')).toBe('chosen');
    setSessionId(null);
    expect(localStorage.getItem('conciliacion.sessionId')).toBeNull();
  });
  it('adopts a response id only when no id is set', async () => {
    const adapter: AxiosAdapter = async (config) => ({ data: {}, status: 200, statusText: 'OK', headers: { 'x-session-id': 'server' }, config });
    client.defaults.adapter = adapter;
    setSessionId('chosen');
    await client.get('/test');
    expect(getSessionId()).toBe('chosen');
    setSessionId(null);
    await client.get('/test');
    expect(getSessionId()).toBe('server');
  });
});
