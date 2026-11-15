import { useQuery } from '@tanstack/react-query';
import client from './client';

export interface RecentSession {
  session_id: string;
  created_at: string;
  last_used_at: string;
  expires_at: string;
  design_filename: string | null;
  topo_filename: string | null;
  n_sections: number;
  n_results: number;
  process_status: string;
}

export interface RecentSessionsResponse {
  ttl_days: number;
  sessions: RecentSession[];
}

export function useRecentSessions() {
  return useQuery({
    queryKey: ['recent-sessions'],
    queryFn: async () => (await client.get<RecentSessionsResponse>('/session/list', { params: { limit: 50 } })).data,
    retry: false,
    refetchOnWindowFocus: false,
  });
}
