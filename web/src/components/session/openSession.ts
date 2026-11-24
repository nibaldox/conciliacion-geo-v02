import type { QueryClient } from '@tanstack/react-query';
import { setSessionId } from '../../api/client';
import { useSession } from '../../stores/session';

export function openSession(id: string, queryClient: QueryClient) {
  setSessionId(id);
  queryClient.clear();
  useSession.getState().reset();
  window.location.reload();
}
