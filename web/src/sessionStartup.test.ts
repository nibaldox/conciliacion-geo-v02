import { beforeEach, describe, expect, it } from 'vitest';
import type { AxiosAdapter } from 'axios';
import client, { getSessionId, setSessionId } from './api/client';
import { restoreSessionFromHash } from './sessionRecovery';
import { useSession } from './stores/session';

const id = '80b2aef4-5f6f-4b43-8621-d5badeec61de';
describe('startup session', () => {
  beforeEach(() => { setSessionId(null); localStorage.clear(); window.history.replaceState(null, '', '/'); useSession.getState().reset(); });
  it('restores stored session and meshes', async () => {
    localStorage.setItem('conciliacion.sessionId', id);
    const headers: string[] = [];
    client.defaults.adapter = (async config => { headers.push(String(config.headers['X-Session-ID'])); return { config, data: { session_id: id, design_mesh_id: 'design', topo_mesh_id: 'topo' }, status: 200, statusText: 'OK', headers: {} }; }) as AxiosAdapter;
    await restoreSessionFromHash();
    expect(headers).toEqual([id]);
    expect(useSession.getState().designMeshId).toBe('design');
    expect(useSession.getState().topoMeshId).toBe('topo');
  });
  it('keeps the stored id on network failure', async () => {
    localStorage.setItem('conciliacion.sessionId', id);
    client.defaults.adapter = async () => { throw new Error('network'); };
    await restoreSessionFromHash();
    expect(getSessionId()).toBe(id);
    expect(localStorage.getItem('conciliacion.sessionId')).toBe(id);
  });
  it('keeps a missing stored session', async () => {
    localStorage.setItem('conciliacion.sessionId', id);
    client.defaults.adapter = async () => { throw { response: { status: 404 } }; };
    await restoreSessionFromHash();
    expect(getSessionId()).toBe(id);
    expect(localStorage.getItem('conciliacion.sessionId')).toBe(getSessionId());
  });
  it('generates a v4 UUID without randomUUID', async () => {
    const original = crypto.randomUUID;
    Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: undefined });
    try {
      await restoreSessionFromHash();
      expect(getSessionId()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    } finally { Object.defineProperty(crypto, 'randomUUID', { configurable: true, value: original }); }
  });
  it('generates one id before parallel requests', async () => {
    const headers: string[] = [];
    client.defaults.adapter = (async config => { headers.push(String(config.headers['X-Session-ID'])); return { config, data: {}, status: 200, statusText: 'OK', headers: {} }; }) as AxiosAdapter;
    await restoreSessionFromHash();
    await Promise.all([client.get('/one'), client.get('/two')]);
    expect(getSessionId()).toMatch(/^[0-9a-f-]{36}$/);
    expect(headers).toEqual([getSessionId(), getSessionId()]);
  });
});
