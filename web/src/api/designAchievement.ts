import { useQuery } from '@tanstack/react-query';
import client from './client';
import { useResults, useSettings } from './hooks';
import { useSession } from '../stores/session';
import type { ResultFilterState } from '../components/results/resultFilters';

export interface DesignAchievementSummary {
  global_score: number | null;
  n_total: number;
  n_evaluable: number;
  crest_cumple: number;
  crest_denom: number;
  crest_pct: number | null;
  toe_cumple: number;
  toe_denom: number;
  toe_pct: number | null;
  berm_cumple: number;
  berm_denom: number;
  berm_pct: number | null;
  delta_crest_mean: number | null;
  delta_toe_mean: number | null;
}

export interface DesignAchievementSectorRow extends DesignAchievementSummary {
  sector: string;
}

export interface DesignAchievementMetadata {
  source: string;
  status: 'computed' | 'no_data';
  assumptions: string[];
}

export interface DesignAchievementResponse {
  session_id: string | null;
  n_total_rows: number;
  summary: DesignAchievementSummary;
  sectors: DesignAchievementSectorRow[];
  tolerances: { neg: number; pos: number };
  tolerances_source: 'core_default' | 'session';
  filters: { sector: string[]; section: string[]; level: string[]; bench: string[] };
  units: { corrections: 'm'; score: '0-100' };
  status_model: string;
  warnings: string[];
  metadata?: DesignAchievementMetadata;
}

export interface UseDesignAchievementResult {
  data: DesignAchievementResponse | null;
  isPending: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  isDemo: boolean;
  refetch: () => void;
}

export function buildDesignAchievementQuery(filters: ResultFilterState): string {
  const params = new URLSearchParams();
  for (const v of filters.sector) params.append('sector', v);
  for (const v of filters.section) params.append('section', v);
  for (const v of filters.level) params.append('level', v);
  for (const v of filters.bench) params.append('bench', String(v));
  return params.toString();
}

export function useDesignAchievement(filters: ResultFilterState): UseDesignAchievementResult {
  const demoMode = useSession((s) => s.demoMode);
  const settings = useSettings();
  const results = useResults();
  const qs = buildDesignAchievementQuery(filters);

  const query = useQuery({
    queryKey: ['design-achievement', qs, settings.dataUpdatedAt, results.dataUpdatedAt],
    queryFn: async () => {
      const url = qs
        ? `/process/design-achievement?${qs}`
        : '/process/design-achievement';
      const { data } = await client.get<DesignAchievementResponse>(url);
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
