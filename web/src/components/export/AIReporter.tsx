import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation } from '@tanstack/react-query';
import client from '../../api/client';
import { useResults, useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';
import { Button } from '../ui/Button';
import type { ComparisonResult, SectionResponse } from '../../api/types';

interface AIUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  is_synthetic: boolean;
}

interface AIResponseChunk {
  content: string;
  finish_reason: 'stop' | 'length' | 'error' | null;
  usage: AIUsage | null;
  cached: boolean;
  chunk_index: number;
}

interface AIHealthResponse {
  status: string;
  version?: string;
  providers?: string[];
}

interface AIProvidersResponse {
  providers: string[];
}

interface AIRequestBody {
  results: Record<string, unknown>;
  sections: SectionResponse[] | null;
  provider: string;
  model: string;
  stream: boolean;
  metadata: Record<string, unknown>;
}

type AIErrorKind = 'rate_limited' | 'server' | 'network';

interface AIErrorState {
  kind: AIErrorKind;
  detail: string;
  retryAfter?: number;
}

const PROVIDER_DEFAULT_MODELS: Record<string, string> = {
  ollama: 'llama3.1:8b',
  lmstudio: 'loaded-model',
  openai: 'gpt-4o-mini',
  openrouter: 'nvidia/nemotron-3-ultra-550b-a55b:free',
  minimax: 'MiniMax-M3',
  glm: 'glm-5.2',
  grok: 'grok-4.20',
};

const HEALTH_REFETCH_MS = 30_000;
const RATE_LIMIT_COUNTDOWN_CAP_SECONDS = 60;

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

function readHeader(headers: unknown, key: string): string | undefined {
  if (!headers || typeof headers !== 'object') return undefined;
  const h = headers as Record<string, unknown>;
  if (typeof h.get === 'function') {
    const v = (h.get as (k: string) => unknown)(key);
    return typeof v === 'string' ? v : undefined;
  }
  const lower = h[key.toLowerCase()];
  if (typeof lower === 'string') return lower;
  const raw = h[key];
  return typeof raw === 'string' ? raw : undefined;
}

function classifyError(err: unknown): AIErrorState {
  if (!err || typeof err !== 'object') {
    return { kind: 'network', detail: '' };
  }
  const e = err as {
    response?: { status?: number; data?: { detail?: string }; headers?: unknown };
    message?: string;
  };
  const status = e.response?.status;
  if (status === 429) {
    const raw = readHeader(e.response?.headers, 'retry-after');
    const parsed = raw ? Number.parseInt(raw, 10) : NaN;
    return {
      kind: 'rate_limited',
      detail: '',
      retryAfter: Number.isFinite(parsed) ? parsed : undefined,
    };
  }
  if (status === 502 || status === 504) {
    return { kind: 'server', detail: e.response?.data?.detail ?? '' };
  }
  if (status === undefined) {
    return { kind: 'network', detail: '' };
  }
  return { kind: 'server', detail: e.response?.data?.detail ?? e.message ?? '' };
}

export function AIReporter() {
  const { t } = useTranslation();
  const { demoMode } = useSession();
  const health = useAIHealth();
  const healthState: 'pending' | 'ok' | 'unavailable' = health.isLoading
    ? 'pending'
    : health.isError || health.data?.status !== 'ok'
      ? 'unavailable'
      : 'ok';

  const providersQuery = useAIProviders(healthState === 'ok');
  const resultsQuery = useResults();
  const sectionsQuery = useSections();
  const hasResults = !!resultsQuery.data && resultsQuery.data.length > 0;

  const [provider, setProvider] = useState<string>('');
  const [model, setModel] = useState<string>('');
  const [notes, setNotes] = useState<string>('');
  const [report, setReport] = useState<AIResponseChunk | null>(null);
  const [errorState, setErrorState] = useState<AIErrorState | null>(null);
  const [countdown, setCountdown] = useState<number>(0);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    if (!provider && providersQuery.data?.providers?.length) {
      const first = providersQuery.data.providers[0];
      setProvider(first);
      setModel(PROVIDER_DEFAULT_MODELS[first] ?? '');
    }
  }, [providersQuery.data, provider]);

  useEffect(() => {
    if (errorState?.kind !== 'rate_limited' || !errorState.retryAfter) {
      setCountdown(0);
      return;
    }
    const start = Math.min(
      Math.max(errorState.retryAfter, 1),
      RATE_LIMIT_COUNTDOWN_CAP_SECONDS,
    );
    setCountdown(start);
    const id = window.setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          window.clearInterval(id);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
    return () => window.clearInterval(id);
  }, [errorState]);

  const generate = useMutation<AIResponseChunk, unknown, AIRequestBody>({
    mutationFn: (payload) =>
      client.post<AIResponseChunk>('/ai/generate', payload).then((r) => r.data),
    onSuccess: (data) => {
      setReport(data);
      setErrorState(null);
    },
    onError: (err) => {
      setErrorState(classifyError(err));
    },
  });

  const generating = generate.isPending;
  const formDisabled =
    healthState !== 'ok' ||
    !hasResults ||
    !provider ||
    !model ||
    generating ||
    countdown > 0;

  const handleProviderChange = (next: string) => {
    setProvider(next);
    setModel(PROVIDER_DEFAULT_MODELS[next] ?? '');
  };

  const handleGenerate = () => {
    if (formDisabled) return;
    setReport(null);
    setErrorState(null);
    setCopied(false);
    const comparisons: ComparisonResult[] = resultsQuery.data ?? [];
    const sections: SectionResponse[] = sectionsQuery.data ?? [];
    const payload: AIRequestBody = {
      results: { comparisons },
      sections,
      provider,
      model,
      stream: false,
      metadata: notes.trim() ? { notes: notes.trim() } : {},
    };
    generate.mutate(payload);
  };

  const handleCopy = async () => {
    if (!report?.content) return;
    try {
      await navigator.clipboard.writeText(report.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const healthLabel =
    healthState === 'ok'
      ? t('ai_reporter.health.ok')
      : healthState === 'unavailable'
        ? t('ai_reporter.health.unavailable')
        : t('ai_reporter.health.pending');
  const healthIcon =
    healthState === 'ok' ? '✓' : healthState === 'unavailable' ? '⚠' : '…';

  const showUnavailable = healthState === 'unavailable';
  const showEmptyState = !hasResults && !demoMode && healthState === 'ok';
  const showForm = healthState === 'ok' && (hasResults || demoMode);

  return (
    <div data-slot="ai-reporter" className="space-y-5">
      <div
        className="rounded-xl shadow-sm p-5"
        style={{
          backgroundColor: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
        }}
      >
        <div className="flex items-center justify-between gap-3">
          <h4
            className="text-sm font-semibold"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {t('ai_reporter.title')}
          </h4>
          <span
            className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full"
            style={{
              backgroundColor: 'var(--color-accent-soft)',
              color: 'var(--color-text-muted)',
            }}
          >
            {t('ai_reporter.ready_badge')}
          </span>
        </div>

        <div className="flex items-center gap-3 mt-3">
          <span aria-hidden="true" className="text-base">
            {healthIcon}
          </span>
          <div className="flex-1 min-w-0">
            <div
              className="text-[10px] uppercase tracking-wider mb-0.5"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              {t('ai_reporter.backend_status')}
            </div>
            <div
              className="text-xs font-medium"
              style={{ color: 'var(--color-text-primary)' }}
              data-testid="ai-reporter-health"
            >
              {healthLabel}
            </div>
          </div>
        </div>
      </div>

      {showUnavailable && (
        <div
          className="rounded-xl shadow-sm p-5"
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
          }}
          data-testid="ai-reporter-unavailable"
        >
          <h5
            className="text-sm font-semibold mb-1"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {t('ai_reporter.error.unavailable_title')}
          </h5>
          <p
            className="text-xs leading-relaxed"
            style={{ color: 'var(--color-text-muted)' }}
          >
            {t('ai_reporter.error.unavailable_description')}
          </p>
        </div>
      )}

      {showEmptyState && (
        <div
          className="rounded-xl shadow-sm p-5"
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
          }}
          data-testid="ai-reporter-empty"
        >
          <h5
            className="text-sm font-semibold mb-1"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {t('ai_reporter.empty.no_data_title')}
          </h5>
          <p
            className="text-xs leading-relaxed"
            style={{ color: 'var(--color-text-muted)' }}
          >
            {t('ai_reporter.empty.no_data_description')}
          </p>
        </div>
      )}

      {showForm && (
        <div
          className="rounded-xl shadow-sm p-5 space-y-3"
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
          }}
          data-testid="ai-reporter-form"
        >
          <div>
            <label
              htmlFor="ai-provider"
              className="block text-xs font-medium mb-1"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              {t('ai_reporter.form.provider_label')}
            </label>
            <select
              id="ai-provider"
              value={provider}
              onChange={(e) => handleProviderChange(e.target.value)}
              disabled={!providersQuery.data?.providers?.length}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
                backgroundColor: 'var(--color-surface)',
              }}
            >
              {!(providersQuery.data?.providers?.length) && (
                <option value="">{t('ai_reporter.health.pending')}</option>
              )}
              {(providersQuery.data?.providers ?? []).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor="ai-model"
              className="block text-xs font-medium mb-1"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              {t('ai_reporter.form.model_label')}
            </label>
            <input
              id="ai-model"
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="model-name"
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
                backgroundColor: 'var(--color-surface)',
              }}
            />
          </div>

          <div>
            <label
              htmlFor="ai-notes"
              className="block text-xs font-medium mb-1"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              {t('ai_reporter.form.notes_label')}
            </label>
            <textarea
              id="ai-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={t('ai_reporter.form.notes_placeholder')}
              rows={2}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none resize-y"
              style={{
                border: '1px solid var(--color-border)',
                color: 'var(--color-text-primary)',
                backgroundColor: 'var(--color-surface)',
              }}
            />
          </div>

          <Button
            type="button"
            variant="primary"
            fullWidth
            loading={generating}
            disabled={formDisabled}
            onClick={handleGenerate}
          >
            {generating
              ? t('ai_reporter.form.generating')
              : t('ai_reporter.form.generate_button')}
          </Button>
        </div>
      )}

      {errorState && (
        <div
          className="rounded-xl shadow-sm p-4"
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
          }}
          role="alert"
          data-testid="ai-reporter-error"
        >
          <p
            className="text-xs"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {errorState.kind === 'rate_limited' && countdown > 0
              ? t('ai_reporter.error.rate_limited', { seconds: countdown })
              : errorState.kind === 'network'
                ? t('ai_reporter.error.network_error')
                : errorState.detail
                  ? `${t('ai_reporter.error.server_error')}: ${errorState.detail}`
                  : t('ai_reporter.error.server_error')}
          </p>
          {errorState.kind !== 'rate_limited' && (
            <button
              type="button"
              onClick={handleGenerate}
              className="mt-2 text-xs underline"
              style={{ color: 'var(--color-accent)' }}
            >
              {t('common.retry')}
            </button>
          )}
        </div>
      )}

      {report && (
        <div
          className="rounded-xl shadow-sm p-5 space-y-3"
          style={{
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
          }}
          data-testid="ai-reporter-result"
        >
          <div className="flex items-center justify-between gap-3">
            <h5
              className="text-sm font-semibold"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {t('ai_reporter.report.title')}
            </h5>
            <div className="flex items-center gap-2">
              {report.cached && (
                <span
                  className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full"
                  style={{
                    backgroundColor: 'var(--color-accent-soft)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  {t('ai_reporter.report.cached_badge')}
                </span>
              )}
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={handleCopy}
                disabled={!report.content}
              >
                {t('ai_reporter.form.copy_button')}
              </Button>
            </div>
          </div>

          <div
            className="text-xs leading-relaxed"
            style={{
              color: 'var(--color-text-primary)',
              maxHeight: '600px',
              overflowY: 'auto',
              whiteSpace: 'pre-wrap',
              fontFamily: 'var(--font-mono, ui-monospace, monospace)',
            }}
            data-testid="ai-reporter-content"
          >
            {report.content}
          </div>

          {copied && (
            <p
              className="text-[10px]"
              style={{ color: 'var(--color-text-muted)' }}
              data-testid="ai-reporter-copied"
            >
              ✓
            </p>
          )}

          {report.usage && (
            <div
              className="flex items-center flex-wrap gap-2 text-[11px]"
              style={{ color: 'var(--color-text-secondary)' }}
              data-testid="ai-reporter-usage"
            >
              <span>
                {t('ai_reporter.report.tokens_label', {
                  prompt: report.usage.prompt_tokens,
                  completion: report.usage.completion_tokens,
                  total: report.usage.total_tokens,
                })}
              </span>
              {report.usage.is_synthetic && (
                <span
                  className="px-1.5 py-0.5 rounded-full text-[10px]"
                  style={{
                    backgroundColor: 'var(--color-accent-soft)',
                    color: 'var(--color-text-muted)',
                  }}
                >
                  {t('ai_reporter.report.estimated_badge')}
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
