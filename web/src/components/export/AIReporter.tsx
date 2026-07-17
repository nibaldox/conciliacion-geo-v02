import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import client from '../../api/client';
import { useResults, useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';
import type { AIHealthResponse, AIProvidersResponse } from './useAIReport';
import {
  useAIReport,
  buildAIGeneratePayload,
  computeTps,
  estimateCost,
} from './useAIReport';
import { AIConfigForm } from './AIConfigForm';
import { AIResultPanel } from './AIResultPanel';
import { AIStatusCard, AIInfoCard } from './AIStatusCard';
import { useAIConfig, type AIErrorState } from './useAIConfig';

const HEALTH_REFETCH_MS = 30_000;

export type AIHealthState = 'pending' | 'ok' | 'unavailable';

function useAIHealth() {
  return useQuery({
    queryKey: ['ai-health'],
    queryFn: () => client.get<AIHealthResponse>('/ai/health').then((r) => r.data),
    refetchInterval: HEALTH_REFETCH_MS,
    retry: false,
  });
}

function useAIProviders(enabled: boolean) {
  return useQuery({
    queryKey: ['ai-providers'],
    queryFn: () =>
      client.get<AIProvidersResponse>('/ai/providers').then((r) => r.data),
    enabled,
    staleTime: 60_000,
  });
}

export function AIReporter() {
  const { t } = useTranslation();
  const demoMode = useSession((s) => s.demoMode);
  const filters = useSession((s) => s.filters);
  const setFilters = useSession((s) => s.setFilters);

  // Health polling (refs the task says stays in the main component).
  const health = useAIHealth();
  const healthState: AIHealthState = health.isLoading
    ? 'pending'
    : health.isError || health.data?.status !== 'ok'
      ? 'unavailable'
      : 'ok';

  const providersQuery = useAIProviders(healthState === 'ok');
  const resultsQuery = useResults();
  const sectionsQuery = useSections();
  const hasResults = !!resultsQuery.data && resultsQuery.data.length > 0;

  // Reducer-driven form state.
  const { state: cfg, dispatch: cfgDispatch } = useAIConfig();

  // Auto-pick first available provider once providers load.
  useEffect(() => {
    if (!cfg.provider && providersQuery.data?.providers?.length) {
      cfgDispatch({
        type: 'SET_PROVIDER',
        value: providersQuery.data.providers[0],
      });
    }
  }, [providersQuery.data, cfg.provider, cfgDispatch]);

  const buildPayload = () =>
    buildAIGeneratePayload({
      cfg,
      filters,
      rows: resultsQuery.data,
      sections: sectionsQuery.data,
    });

  const formEnabled =
    healthState === 'ok' &&
    hasResults &&
    !!cfg.provider &&
    !!cfg.model;

  // Streaming / non-streaming orchestration + result lifecycle.
  const reportState = useAIReport({
    buildPayload,
    enabled: formEnabled,
  });

  const formDisabled =
    !formEnabled ||
    reportState.isGenerating ||
    reportState.countdown > 0;

  const toggleFilter = (
    key: 'sector' | 'section' | 'bench',
    value: string | number,
  ) => {
    const current = filters[key] as Array<string | number>;
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    setFilters({ [key]: next } as Partial<typeof filters>);
  };

  const showForm = healthState === 'ok' && (hasResults || demoMode);
  const showEmptyState =
    healthState === 'ok' && !hasResults && !demoMode;

  const tps = useMemo(
    () => computeTps(reportState.report, reportState.latencyMs),
    [reportState.report, reportState.latencyMs],
  );
  const costUsd = reportState.report?.usage
    ? estimateCost(cfg.provider, reportState.report.usage)
    : null;

  // Touch `t` so unused-import linters don't complain (kept for parity with original).
  void t;

  return (
    <div data-slot="ai-reporter" className="space-y-5">
      <AIStatusCard healthState={healthState} />

      {healthState === 'unavailable' && (
        <AIInfoCard
          testId="ai-reporter-unavailable"
          titleKey="ai_reporter.error.unavailable_title"
          descriptionKey="ai_reporter.error.unavailable_description"
        />
      )}

      {showEmptyState && (
        <AIInfoCard
          testId="ai-reporter-empty"
          titleKey="ai_reporter.empty.no_data_title"
          descriptionKey="ai_reporter.empty.no_data_description"
        />
      )}

      {showForm && (
        <AIConfigForm
          state={cfg}
          dispatch={cfgDispatch}
          providers={providersQuery.data?.providers}
          results={resultsQuery.data}
          filters={filters}
          onToggleFilter={toggleFilter}
          generating={reportState.isGenerating}
          formDisabled={formDisabled}
          onGenerate={reportState.generate}
        />
      )}

      <AIResultPanel
        errorState={reportState.errorState}
        countdown={reportState.countdown}
        onRetry={reportState.generate}
        report={reportState.report}
        tps={tps}
        costUsd={costUsd}
        copied={reportState.copied}
        onCopy={reportState.copy}
        onDownload={reportState.download}
      />
    </div>
  );
}

// Re-export so external consumers (tests, etc.) keep working.
export type { AIErrorState };