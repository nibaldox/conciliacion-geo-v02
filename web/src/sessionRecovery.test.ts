import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSession } from './stores/session';
import { consumeSessionRestoreHash, restoreSessionFromHash } from './sessionRecovery';

const { get, setSessionId } = vi.hoisted(() => ({ get: vi.fn(), setSessionId: vi.fn() }));

vi.mock('./api/client', () => ({
  default: { get },
  setSessionId,
}));

const SESSION_ID = '80b2aef4-5f6f-4b43-8621-d5badeec61de';

describe('session recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSession.getState().reset();
  });

  it('removes the one-time hash before returning its session ID', () => {
    const replaceState = vi.fn();
    const location = { hash: `#restore-session=${SESSION_ID}`, pathname: '/app/', search: '?view=3d' } as Location;
    const history = { state: null, replaceState } as unknown as History;
    expect(consumeSessionRestoreHash(location, history)).toBe(SESSION_ID);
    expect(replaceState).toHaveBeenCalledWith(null, '', '/app/?view=3d');
  });

  it('ignores other hashes and rejects malformed restoration IDs', () => {
    const replaceState = vi.fn();
    const history = { state: null, replaceState } as unknown as History;
    expect(consumeSessionRestoreHash({ hash: '#section', pathname: '/', search: '' } as Location, history)).toBeNull();
    expect(consumeSessionRestoreHash({ hash: '#restore-session=bad', pathname: '/', search: '' } as Location, history)).toBe('');
    expect(replaceState).toHaveBeenCalledTimes(1);
  });

  it('restores mesh IDs only after the API confirms the requested session', async () => {
    setSessionId.mockImplementation(() => undefined);
    get.mockResolvedValue({ data: { session_id: SESSION_ID, design_mesh_id: 'design-1', topo_mesh_id: 'topo-1' } });
    window.history.replaceState(null, '', `/#restore-session=${SESSION_ID}`);
    await restoreSessionFromHash();
    expect(setSessionId).toHaveBeenCalledWith(SESSION_ID);
    expect(get).toHaveBeenCalledWith('/session/recovery');
    expect(useSession.getState().designMeshId).toBe('design-1');
    expect(useSession.getState().topoMeshId).toBe('topo-1');
    expect(window.location.hash).toBe('');
    window.history.replaceState(null, '', '/');
  });
});
