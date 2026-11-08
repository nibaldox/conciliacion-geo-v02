import { useQuery } from '@tanstack/react-query';
import client from './client';
import { useResults, useSettings } from './hooks';
import { useSession } from '../stores/session';
import type { ResultFilterState } from '../components/results/resultFilters.utils';
import type { ProposedComplianceResponse } from './types';

export type { ProposedComplianceResponse };

export interface UseProposedComplianceResult {
  data: ProposedComplianceResponse | null;
  isPending: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  isDemo: boolean;
  refetch: () => void;
}

export function buildProposedComplianceQuery(filters: ResultFilterState): string {
  const params = new URLSearchParams();
  for (const v of filters.sector) params.append('sector', v);
  for (const v of filters.section) params.append('section', v);
  for (const v of filters.level) params.append('level', v);
  for (const v of filters.bench) params.append('bench', String(v));
  return params.toString();
}

export function useProposedCompliance(filters: ResultFilterState): UseProposedComplianceResult {
  const demoMode = useSession((s) => s.demoMode);
  const settings = useSettings();
  const results = useResults();
  const qs = buildProposedComplianceQuery(filters);

  const query = useQuery({
    queryKey: ['proposed-compliance', qs, settings.dataUpdatedAt, results.dataUpdatedAt],
    queryFn: async () => {
      const url = qs
        ? `/process/proposed-compliance?${qs}`
        : '/process/proposed-compliance';
      const { data } = await client.get<ProposedComplianceResponse>(url);
      return data;
    },
    enabled: !demoMode,
  });

  return {
    isPending: demoMode ? false : query.isPending,
    data: demoMode ? null : (query.data ?? null),
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    isDemo: demoMode,
    refetch: () => {
      void query.refetch();
    },
  };
}
