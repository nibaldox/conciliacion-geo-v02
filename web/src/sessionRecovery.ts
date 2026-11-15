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

export function newSessionId(): string {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function restoreSessionFromHash(): Promise<boolean> {
  const requestedSessionId = consumeSessionRestoreHash(window.location, window.history);
  let stored: string | null = null;
  try { stored = localStorage.getItem('conciliacion.sessionId'); } catch { stored = null; }
  const isHash = requestedSessionId !== null;
  const sessionId = isHash ? requestedSessionId : stored && SESSION_ID_PATTERN.test(stored) ? stored : null;
  if (!sessionId) {
    setSessionId(newSessionId());
    return isHash;
  }

  setSessionId(sessionId);
  try {
    const { data } = await client.get<SessionRecoveryResponse>('/session/recovery');
    if (data.session_id !== sessionId) throw new Error('Session mismatch');
    const state = useSession.getState();
    state.setDesignMeshId(data.design_mesh_id);
    state.setTopoMeshId(data.topo_mesh_id);
    return false;
  } catch {
    if (!isHash) return false;
    setSessionId(newSessionId());
    const state = useSession.getState();
    state.setDesignMeshId(null);
    state.setTopoMeshId(null);
    return isHash;
  }
}
