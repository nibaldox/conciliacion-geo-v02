import client, { setSessionId } from './api/client';
import { useSession } from './stores/session';

interface SessionRecoveryResponse {
  session_id: string;
  design_mesh_id: string | null;
  topo_mesh_id: string | null;
}

const SESSION_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function consumeSessionRestoreHash(location: Location, history: History): string | null {
  const prefix = '#restore-session=';
  if (!location.hash.startsWith(prefix)) return null;

  const encodedId = location.hash.slice(prefix.length);
  history.replaceState(history.state, '', `${location.pathname}${location.search}`);
  let sessionId: string;
  try {
    sessionId = decodeURIComponent(encodedId);
  } catch {
    return '';
  }
  return SESSION_ID_PATTERN.test(sessionId) ? sessionId : '';
}

export async function restoreSessionFromHash(): Promise<boolean> {
  const requestedSessionId = consumeSessionRestoreHash(window.location, window.history);
  if (requestedSessionId === null) return false;
  if (!requestedSessionId) return true;

  setSessionId(requestedSessionId);
  try {
    const { data } = await client.get<SessionRecoveryResponse>('/session/recovery');
    if (data.session_id !== requestedSessionId) throw new Error('Session mismatch');
    const state = useSession.getState();
    state.setDesignMeshId(data.design_mesh_id);
    state.setTopoMeshId(data.topo_mesh_id);
    return false;
  } catch {
    setSessionId(null);
    const state = useSession.getState();
    state.setDesignMeshId(null);
    state.setTopoMeshId(null);
    return true;
  }
}
